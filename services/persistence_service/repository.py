from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterator, Protocol

from shared.schemas.messages import Channel, InboundMessage
from shared.schemas.tickets import Ticket, TicketPriority, TicketStatus
from shared.utils.ids import new_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_text(value: dict | list | None) -> str:
    return json.dumps(value or {}, default=str, separators=(",", ":"))


class CXRepository(Protocol):
    def migrate(self) -> None: ...
    def reserve_message(self, provider: str, external_message_id: str) -> bool: ...
    def save_idempotent_response(self, provider: str, external_message_id: str, response: dict) -> None: ...
    def get_idempotent_response(self, provider: str, external_message_id: str) -> dict | None: ...
    def resolve_customer(self, message: InboundMessage) -> dict: ...
    def get_or_create_conversation(self, customer_id: str) -> dict: ...
    def list_recent_turns(self, conversation_id: str, limit: int = 8) -> list[dict]: ...
    def append_turn(self, **values) -> dict: ...
    def update_turn_metadata(self, turn_id: str, extra: dict) -> None: ...
    def update_turn_intent_urgency(self, turn_id: str, intent: str, urgency: str) -> None: ...
    def update_conversation_summary(self, conversation_id: str, summary: str) -> None: ...
    def create_ticket(self, ticket: Ticket) -> Ticket: ...
    def update_ticket(self, ticket_id: str, **values) -> dict | None: ...
    def find_active_ticket(self, conversation_id: str) -> Ticket | None: ...
    def find_open_tickets_for_customer(self, customer_id: str, limit: int = 5) -> list[dict]: ...
    def list_tickets(self) -> list[dict]: ...
    def get_ticket(self, ticket_id: str) -> dict | None: ...
    def add_ticket_event(self, ticket_id: str, event_type: str, actor: str, details: dict | None = None) -> dict: ...
    def list_ticket_events(self, ticket_id: str) -> list[dict]: ...
    def add_retrieval_evidence(self, turn_id: str, contexts: list[dict]) -> None: ...
    def list_retrieval_evidence(self, turn_id: str | None = None) -> list[dict]: ...
    def record_whatsapp_delivery_status(self, status: dict) -> dict: ...
    def list_whatsapp_delivery_statuses(self, provider_message_id: str | None = None, limit: int = 50) -> list[dict]: ...
    def add_audit_event(self, event_type: str, correlation_id: str, **values) -> None: ...
    def list_audit_events(self, correlation_id: str | None = None) -> list[dict]: ...
    def get_conversation(self, conversation_id: str) -> dict | None: ...
    def list_conversations(self) -> list[dict]: ...
    def list_customer_identifiers(self, customer_id: str) -> list[dict]: ...
    def create_admin_user(self, username: str, email: str, password_hash: str) -> dict: ...
    def get_admin_user_by_username(self, username: str) -> dict | None: ...
    def get_admin_user_by_email(self, email: str) -> dict | None: ...
    def list_admin_users(self) -> list[dict]: ...
    def create_customer_user(self, user_id: str, email: str, password_hash: str) -> dict: ...
    def get_customer_user_by_id(self, user_id: str) -> dict | None: ...
    def get_customer_user_by_email(self, email: str) -> dict | None: ...


class SQLiteCXRepository:
    def __init__(self, database_path: str = "data/cx_phase1.db") -> None:
        self.database_path = database_path
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self.database_path == ":memory:":
                if self._connection is None:
                    self._connection = sqlite3.connect(":memory:", check_same_thread=False)
                conn = self._connection
            else:
                conn = sqlite3.connect(self.database_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            finally:
                if self.database_path != ":memory:":
                    conn.close()

    def migrate(self) -> None:
        migrations = sorted((Path(__file__).parent / "migrations").glob("*.sql"))
        with self.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for migration in migrations:
                if migration.name in applied:
                    continue
                conn.executescript(migration.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (migration.name, utc_now()),
                )

    def reserve_message(self, provider: str, external_message_id: str) -> bool:
        try:
            with self.connection() as conn:
                conn.execute(
                    "INSERT INTO idempotency_keys(provider, external_message_id, created_at) VALUES (?, ?, ?)",
                    (provider, external_message_id, utc_now()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def save_idempotent_response(self, provider: str, external_message_id: str, response: dict) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE idempotency_keys SET response_json = ? WHERE provider = ? AND external_message_id = ?",
                (json_text(response), provider, external_message_id),
            )

    def get_idempotent_response(self, provider: str, external_message_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT response_json FROM idempotency_keys WHERE provider = ? AND external_message_id = ?",
                (provider, external_message_id),
            ).fetchone()
        return json.loads(row["response_json"]) if row and row["response_json"] else None

    def resolve_customer(self, message: InboundMessage) -> dict:
        identifiers = []
        portal_user_id = message.metadata.get("portal_user_id")
        portal_graph_customer_id = message.metadata.get("portal_graph_customer_id")
        if portal_user_id:
            identifiers.append(("portal", str(portal_user_id).strip()))
        if portal_graph_customer_id:
            identifiers.append(("graph", str(portal_graph_customer_id).strip()))
        identifiers.append((message.channel.value, message.channel_identifier))
        linked_email = message.metadata.get("linked_email")
        linked_phone = message.metadata.get("linked_phone")
        if linked_email:
            identifiers.append((Channel.EMAIL.value, str(linked_email).strip().lower()))
        if linked_phone:
            phone = str(linked_phone).strip().lstrip("+")
            identifiers.append((Channel.WHATSAPP.value, phone))
            # Also try with 91 country-code prefix: BFSI data stores bare 10-digit numbers
            # but WhatsApp channel identifiers arrive and are stored with the prefix.
            if len(phone) == 10:
                identifiers.append((Channel.WHATSAPP.value, "91" + phone))
        lookup_identifiers = identifiers
        if portal_user_id or portal_graph_customer_id:
            lookup_identifiers = [
                item for item in identifiers
                if item[0] in {"portal", "graph", Channel.EMAIL.value}
            ]

        with self.connection() as conn:
            customer_id = None
            for channel, identifier in lookup_identifiers:
                row = conn.execute(
                    "SELECT customer_id FROM channel_identities WHERE channel = ? AND identifier = ?",
                    (channel, identifier),
                ).fetchone()
                if row:
                    customer_id = row["customer_id"]
                    break
            now = utc_now()
            if not customer_id:
                customer_id = new_id("cust")
                conn.execute(
                    "INSERT INTO customers(customer_id, display_name, metadata_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (customer_id, message.display_name, json_text(message.profile_metadata), now, now),
                )
            else:
                row = conn.execute("SELECT metadata_json FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
                metadata = json.loads(row["metadata_json"] or "{}")
                metadata.update(message.profile_metadata)
                conn.execute(
                    "UPDATE customers SET display_name = COALESCE(?, display_name), metadata_json = ?, updated_at = ? "
                    "WHERE customer_id = ?",
                    (message.display_name, json_text(metadata), now, customer_id),
                )
            for channel, identifier in identifiers:
                conn.execute(
                    "INSERT OR IGNORE INTO channel_identities(identity_id, customer_id, channel, identifier, "
                    "metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (new_id("ident"), customer_id, channel, identifier, "{}", now),
                )
            row = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        return result

    def get_or_create_conversation(self, customer_id: str) -> dict:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE customer_id = ? ORDER BY created_at DESC LIMIT 1",
                (customer_id,),
            ).fetchone()
            now = utc_now()
            if not row:
                conversation_id = new_id("conv")
                conn.execute(
                    "INSERT INTO conversations(conversation_id, customer_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (conversation_id, customer_id, now, now),
                )
                row = conn.execute(
                    "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
                ).fetchone()
            elif dict(row)["status"] in ("resolved", "closed"):
                # Reopen the existing conversation when the customer messages again
                conn.execute(
                    "UPDATE conversations SET status = 'active', updated_at = ? WHERE conversation_id = ?",
                    (now, dict(row)["conversation_id"]),
                )
                row = conn.execute(
                    "SELECT * FROM conversations WHERE conversation_id = ?", (dict(row)["conversation_id"],)
                ).fetchone()
        return dict(row)

    def list_recent_turns(self, conversation_id: str, limit: int = 8) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [self._turn_dict(row) for row in reversed(rows)]

    def update_turn_metadata(self, turn_id: str, extra: dict) -> None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM conversation_turns WHERE turn_id = ?", (turn_id,)
            ).fetchone()
            metadata = json.loads(row["metadata_json"] or "{}") if row else {}
            metadata.update(extra)
            conn.execute(
                "UPDATE conversation_turns SET metadata_json = ? WHERE turn_id = ?",
                (json_text(metadata), turn_id),
            )

    def update_turn_intent_urgency(self, turn_id: str, intent: str, urgency: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE conversation_turns SET intent = ?, urgency = ? WHERE turn_id = ?",
                (intent, urgency, turn_id),
            )

    def append_turn(self, **values) -> dict:
        turn_id = values.get("turn_id") or new_id("turn")
        created_at = values.get("created_at") or utc_now()
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO conversation_turns(turn_id, conversation_id, customer_id, channel, direction, text, "
                "external_message_id, subject, intent, urgency, resolved, ticket_id, metadata_json, delivery_status, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    turn_id, values["conversation_id"], values["customer_id"], values["channel"],
                    values["direction"], values["text"], values.get("external_message_id"), values.get("subject"),
                    values.get("intent"), values.get("urgency"), values.get("resolved"), values.get("ticket_id"),
                    json_text(values.get("metadata")), values.get("delivery_status"), created_at,
                ),
            )
            if values.get("resolved"):
                conn.execute(
                    "UPDATE conversations SET status = 'resolved', updated_at = ? WHERE conversation_id = ?",
                    (created_at, values["conversation_id"]),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                    (created_at, values["conversation_id"]),
                )
            row = conn.execute("SELECT * FROM conversation_turns WHERE turn_id = ?", (turn_id,)).fetchone()
        return self._turn_dict(row)

    def update_conversation_summary(self, conversation_id: str, summary: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE conversations SET summary = ?, updated_at = ? WHERE conversation_id = ?",
                (summary, utc_now(), conversation_id),
            )

    def create_ticket(self, ticket: Ticket) -> Ticket:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO tickets(ticket_id, conversation_id, customer_id, title, description, intent, priority, "
                "assigned_team, status, external_ticket_id, external_ticket_url, crm_sync_status, crm_sync_error, "
                "approval_status, escalation_reason, sla_due_at, metadata_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket.ticket_id, ticket.conversation_id, ticket.customer_id, ticket.title, ticket.description,
                    ticket.intent, ticket.priority.value, ticket.assigned_team, ticket.status.value,
                    ticket.external_ticket_id, ticket.external_ticket_url, ticket.crm_sync_status,
                    ticket.crm_sync_error, ticket.approval_status, ticket.escalation_reason,
                    ticket.sla_due_at.isoformat() if ticket.sla_due_at else None, json_text(ticket.metadata),
                    ticket.created_at.isoformat(), ticket.updated_at.isoformat(),
                ),
            )
        return ticket

    def update_ticket(self, ticket_id: str, **values) -> dict | None:
        allowed = {
            "status", "external_ticket_id", "external_ticket_url", "crm_sync_status", "crm_sync_error",
            "approval_status", "escalation_reason", "sla_due_at", "metadata_json",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return self.get_ticket(ticket_id)
        updates["updated_at"] = utc_now()
        with self.connection() as conn:
            conn.execute(
                f"UPDATE tickets SET {', '.join(f'{key} = ?' for key in updates)} WHERE ticket_id = ?",
                (*updates.values(), ticket_id),
            )
        return self.get_ticket(ticket_id)

    def find_active_ticket(self, conversation_id: str) -> Ticket | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE conversation_id = ? AND status != 'resolved' ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return self._ticket(row) if row else None

    def find_open_tickets_for_customer(self, customer_id: str, limit: int = 5) -> list[dict]:
        """Return all open (non-resolved) tickets for a customer across all channels."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE customer_id = ? AND status != 'resolved' "
                "ORDER BY created_at DESC LIMIT ?",
                (customer_id, limit),
            ).fetchall()
        return [self._ticket_dict(row) for row in rows]

    def list_tickets(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
        return [self._ticket_dict(row) for row in rows]

    def get_ticket(self, ticket_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return self._ticket_dict(row) if row else None

    def add_ticket_event(self, ticket_id: str, event_type: str, actor: str, details: dict | None = None) -> dict:
        ticket_event_id = new_id("tevt")
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO ticket_events(ticket_event_id, ticket_id, event_type, actor, details_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ticket_event_id, ticket_id, event_type, actor, json_text(details), utc_now()),
            )
            row = conn.execute(
                "SELECT * FROM ticket_events WHERE ticket_event_id = ?", (ticket_event_id,)
            ).fetchone()
        return self._json_fields(dict(row), "details_json")

    def list_ticket_events(self, ticket_id: str) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ticket_events WHERE ticket_id = ? ORDER BY created_at", (ticket_id,)
            ).fetchall()
        return [self._json_fields(dict(row), "details_json") for row in rows]

    def add_retrieval_evidence(self, turn_id: str, contexts: list[dict]) -> None:
        with self.connection() as conn:
            for context in contexts:
                metadata = context.get("metadata", {})
                conn.execute(
                    "INSERT INTO retrieval_evidence(evidence_id, turn_id, source, document_version, chunk_text, "
                    "score, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id("ev"), turn_id, metadata.get("source", "unknown"),
                        metadata.get("document_version"), context.get("text", ""), float(context.get("score", 0)),
                        json_text(metadata), utc_now(),
                    ),
                )

    def list_retrieval_evidence(self, turn_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM retrieval_evidence"
        args: tuple = ()
        if turn_id:
            query += " WHERE turn_id = ?"
            args = (turn_id,)
        query += " ORDER BY created_at"
        with self.connection() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._json_fields(dict(row), "metadata_json") for row in rows]

    def record_whatsapp_delivery_status(self, status: dict) -> dict:
        provider_message_id = status["provider_message_id"]
        turn = self._find_turn_by_provider_message_id(provider_message_id)
        event_id = new_id("wastat")
        created_at = utc_now()
        with self.connection() as conn:
            if turn:
                conn.execute(
                    "UPDATE conversation_turns SET delivery_status = ? WHERE turn_id = ?",
                    (status["status"], turn["turn_id"]),
                )
            conn.execute(
                "INSERT INTO whatsapp_delivery_statuses(status_event_id, provider_message_id, status, recipient_id, "
                "conversation_id, turn_id, timestamp, error_code, error_title, error_details, raw_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    provider_message_id,
                    status["status"],
                    status.get("recipient_id"),
                    turn["conversation_id"] if turn else None,
                    turn["turn_id"] if turn else None,
                    status.get("timestamp"),
                    status.get("error_code"),
                    status.get("error_title"),
                    status.get("error_details"),
                    json_text(status.get("raw")),
                    created_at,
                ),
            )
            row = conn.execute(
                "SELECT * FROM whatsapp_delivery_statuses WHERE status_event_id = ?", (event_id,)
            ).fetchone()
        return self._json_fields(dict(row), "raw_json")

    def list_whatsapp_delivery_statuses(
        self, provider_message_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        query = "SELECT * FROM whatsapp_delivery_statuses"
        args: tuple = ()
        if provider_message_id:
            query += " WHERE provider_message_id = ?"
            args = (provider_message_id,)
        query += " ORDER BY created_at DESC LIMIT ?"
        args = (*args, limit)
        with self.connection() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._json_fields(dict(row), "raw_json") for row in rows]

    def _find_turn_by_provider_message_id(self, provider_message_id: str) -> dict | None:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_turns WHERE channel = ? AND direction = 'outbound' ORDER BY created_at DESC",
                (Channel.WHATSAPP.value,),
            ).fetchall()
        for row in rows:
            turn = self._turn_dict(row)
            metadata = turn.get("metadata", {})
            if metadata.get("provider_message_id") == provider_message_id:
                return turn
        return None

    def add_audit_event(self, event_type: str, correlation_id: str, **values) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO audit_events(event_id, event_type, correlation_id, customer_id, conversation_id, "
                "message_id, intent, ticket_id, channel, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("audit"), event_type, correlation_id, values.get("customer_id"),
                    values.get("conversation_id"), values.get("message_id"), values.get("intent"),
                    values.get("ticket_id"), values.get("channel"), json_text(values.get("details")), utc_now(),
                ),
            )

    def list_audit_events(self, correlation_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM audit_events"
        args: tuple = ()
        if correlation_id:
            query += " WHERE correlation_id = ?"
            args = (correlation_id,)
        query += " ORDER BY created_at"
        with self.connection() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._json_fields(dict(row), "details_json") for row in rows]

    def get_conversation(self, conversation_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["turns"] = self.list_recent_turns(conversation_id, limit=100)
        return result

    def list_conversations(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.*,
                    cu.display_name,
                    cu.created_at AS customer_since,
                    (SELECT channel FROM conversation_turns
                     WHERE conversation_id = c.conversation_id
                     ORDER BY created_at DESC LIMIT 1) AS last_channel,
                    (SELECT text FROM conversation_turns
                     WHERE conversation_id = c.conversation_id AND direction = 'inbound'
                     ORDER BY created_at DESC LIMIT 1) AS last_message,
                    (SELECT intent FROM conversation_turns
                     WHERE conversation_id = c.conversation_id AND intent IS NOT NULL AND intent != ''
                     ORDER BY created_at DESC LIMIT 1) AS last_intent,
                    (SELECT urgency FROM conversation_turns
                     WHERE conversation_id = c.conversation_id AND urgency IS NOT NULL
                     ORDER BY created_at DESC LIMIT 1) AS last_urgency
                FROM conversations c
                LEFT JOIN customers cu ON c.customer_id = cu.customer_id
                ORDER BY c.updated_at DESC

                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_customer_identifiers(self, customer_id: str) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT channel, identifier FROM channel_identities WHERE customer_id = ?",
                (customer_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_admin_user(self, username: str, email: str, password_hash: str) -> dict:
        now = utc_now()
        with self.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO admin_users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, email, password_hash, now),
            )
            row = conn.execute("SELECT * FROM admin_users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        result = dict(row)
        result.pop("password_hash", None)
        return result

    def get_admin_user_by_username(self, username: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None

    def get_admin_user_by_email(self, email: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM admin_users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def list_admin_users(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, username, email, created_at FROM admin_users ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_customer_user(self, user_id: str, email: str, password_hash: str) -> dict:
        now = utc_now()
        with self.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO customer_users (user_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, email, password_hash, now),
            )
            row = conn.execute("SELECT * FROM customer_users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        result = dict(row)
        result.pop("password_hash", None)
        return result

    def get_customer_user_by_id(self, user_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM customer_users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_customer_user_by_email(self, email: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM customer_users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _json_fields(value: dict, *fields: str) -> dict:
        for field in fields:
            value[field.removesuffix("_json")] = json.loads(value.pop(field) or "{}")
        return value

    def _turn_dict(self, row: sqlite3.Row) -> dict:
        return self._json_fields(dict(row), "metadata_json")

    @staticmethod
    def _ticket(row: sqlite3.Row) -> Ticket:
        value = SQLiteCXRepository._ticket_dict(row)
        value["priority"] = TicketPriority(value["priority"])
        value["status"] = TicketStatus(value["status"])
        return Ticket(**value)

    @staticmethod
    def _ticket_dict(row: sqlite3.Row) -> dict:
        value = dict(row)
        if "metadata_json" in value:
            value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
        return value
