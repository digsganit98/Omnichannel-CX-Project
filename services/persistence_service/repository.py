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
    def list_recent_turns(self, conversation_id: str, limit: int = 8, channel: str | None = None) -> list[dict]: ...
    def list_conversation_turns(self, conversation_id: str) -> list[dict]: ...
    def count_recent_inbound(self, customer_id: str, since_iso: str) -> int: ...
    def list_customer_turns(self, customer_id: str, limit: int = 40) -> list[dict]: ...
    def get_turn(self, turn_id: str) -> dict | None: ...
    def get_ticket_reply(self, ticket_id: str) -> str | None: ...
    def append_turn(self, **values) -> dict: ...
    def update_turn_metadata(self, turn_id: str, extra: dict) -> None: ...
    def update_turn_intent_urgency(self, turn_id: str, intent: str, urgency: str) -> None: ...
    def update_conversation_summary(self, conversation_id: str, summary: str) -> None: ...
    def get_case_summary(self, conversation_id: str) -> dict | None: ...
    def save_case_summary(self, conversation_id: str, latest_turn_id: str, summary: dict) -> None: ...
    def get_customer_context(self, customer_id: str) -> dict | None: ...
    def save_customer_context(self, customer_id: str, record_hash: str, categories: dict, model: str | None) -> None: ...
    def get_opportunity_evaluation(self, conversation_id: str) -> dict | None: ...
    def save_opportunity_evaluation(self, conversation_id: str, input_hash: str, suppressed: str | None) -> None: ...
    def create_ticket(self, ticket: Ticket) -> Ticket: ...
    def update_ticket(self, ticket_id: str, **values) -> dict | None: ...
    def find_active_ticket(self, conversation_id: str) -> Ticket | None: ...
    def find_active_ticket_for_intent(self, conversation_id: str, intent: str) -> Ticket | None: ...
    def find_active_ticket_for_scope(self, conversation_id: str, intent: str, ticket_scope: str) -> Ticket | None: ...
    def list_active_tickets_for_intent(self, conversation_id: str, intent: str) -> list[Ticket]: ...
    def list_active_tickets_for_conversation(self, conversation_id: str, limit: int = 5) -> list[Ticket]: ...
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
    def add_llm_usage_event(self, event: dict) -> dict: ...
    def list_llm_usage_events(self, limit: int = 100, correlation_id: str | None = None) -> list[dict]: ...
    def get_llm_usage_summary(self, days: int = 7) -> dict: ...
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
    def add_agent_assist_recommendation(self, conversation_id: str, customer_id: str, ticket_id: str | None,
                                         action_type: str, reason: str, confidence: float, priority: int = 0,
                                         metadata: dict | None = None) -> dict: ...
    def list_agent_assist_recommendations(self, conversation_id: str | None = None,
                                           ticket_id: str | None = None,
                                           status: str | None = None) -> list[dict]: ...
    def update_agent_assist_recommendation(self, recommendation_id: str, status: str, actor: str) -> dict | None: ...
    def get_agent_assist_recommendation(self, recommendation_id: str) -> dict | None: ...
    def add_reply_draft(self, conversation_id: str, customer_id: str, channel: str, draft_text: str,
                        ticket_id: str | None = None, inbound_turn_id: str | None = None,
                        hold_reason: str = "", reason_code: str = "",
                        channel_identifier: str | None = None, provider: str | None = None,
                        retrieval_confidence: float | None = None,
                        intent_confidence: float | None = None,
                        offer_product: str | None = None) -> dict: ...
    def list_reply_drafts(self, conversation_id: str | None = None, status: str | None = None) -> list[dict]: ...
    def get_reply_draft(self, draft_id: str) -> dict | None: ...
    def update_reply_draft(self, draft_id: str, status: str, actor: str,
                           sent_text: str | None = None) -> dict | None: ...


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
            elif dict(row)["status"] == "closed":
                # Reopen the existing conversation when the customer messages again
                conn.execute(
                    "UPDATE conversations SET status = 'active', updated_at = ? WHERE conversation_id = ?",
                    (now, dict(row)["conversation_id"]),
                )
                row = conn.execute(
                    "SELECT * FROM conversations WHERE conversation_id = ?", (dict(row)["conversation_id"],)
                ).fetchone()
        return dict(row)

    def list_recent_turns(self, conversation_id: str, limit: int = 8, channel: str | None = None) -> list[dict]:
        with self.connection() as conn:
            if channel:
                rows = conn.execute(
                    "SELECT * FROM conversation_turns WHERE conversation_id = ? AND channel = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (conversation_id, channel, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
                    (conversation_id, limit),
                ).fetchall()
        return [self._turn_dict(row) for row in reversed(rows)]

    def list_conversation_turns(self, conversation_id: str) -> list[dict]:
        """All turns for a conversation, chronological (oldest first). Unlike
        list_recent_turns there is no LIMIT — used to reconstruct a ticket's full
        exchange history."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        return [self._turn_dict(row) for row in rows]

    def count_recent_inbound(self, customer_id: str, since_iso: str) -> int:
        """Number of inbound (customer-sent) turns for a customer since since_iso
        (ISO-8601). Reported as 'contacts_30d' on the customer graph endpoint."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM conversation_turns "
                "WHERE customer_id = ? AND direction = 'inbound' AND created_at >= ?",
                (customer_id, since_iso),
            ).fetchone()
        return row["n"] if row else 0

    def list_customer_turns(self, customer_id: str, limit: int = 40) -> list[dict]:
        """Most recent turns for a customer (any conversation), newest first —
        used by agent-assist for sentiment/urgency signals."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_turns WHERE customer_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (customer_id, limit),
            ).fetchall()
        return [self._turn_dict(row) for row in rows]

    def get_turn(self, turn_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_turns WHERE turn_id = ?", (turn_id,)
            ).fetchone()
        return self._turn_dict(row) if row else None

    def get_ticket_reply(self, ticket_id: str) -> str | None:
        """Latest real outbound reply for a ticket — skips the interim 'holding' message so
        the ticket detail shows the actual answer, not 'a support agent will help you...'."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT text FROM conversation_turns WHERE ticket_id = ? AND direction = 'outbound' "
                "ORDER BY created_at DESC",
                (ticket_id,),
            ).fetchall()
        for row in rows:
            text = row["text"] or ""
            if "will help you with this shortly" not in text:
                return text
        return rows[0]["text"] if rows else None

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
            # A turn marked resolved closes ONE ticket, not the customer's whole case load.
            # This used to flip the conversation unconditionally, so a customer confirming
            # one matter closed a conversation that still had other tickets open — the agent
            # then saw a green "resolved" banner over live work. Same rule the admin UI
            # already applies when an agent resolves a ticket by hand (app.js doResolve):
            # resolved only when nothing is left open. Counted in THIS transaction so the
            # just-resolved ticket is already committed and cannot be double-counted.
            if values.get("resolved"):
                still_open = conn.execute(
                    "SELECT COUNT(*) FROM tickets WHERE conversation_id = ? AND status != 'closed'",
                    (values["conversation_id"],),
                ).fetchone()[0]
                conn.execute(
                    "UPDATE conversations SET status = ?, updated_at = ? WHERE conversation_id = ?",
                    ("active" if still_open else "closed", created_at, values["conversation_id"]),
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

    def get_case_summary(self, conversation_id: str) -> dict | None:
        """The cached agent-facing summary, or None. Callers compare latest_turn_id
        against the conversation's newest turn to decide whether it is still current."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM case_summaries WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        # open_items was dropped: every value it ever produced was either a reworded
        # copy of `situation` or empty. The column stays (NOT NULL, written as [])
        # so no table rebuild is needed, but nothing reads it.
        record.pop("open_items_json", None)
        return record

    def save_case_summary(self, conversation_id: str, latest_turn_id: str, summary: dict) -> None:
        """Upsert: one summary per conversation, replaced whenever it is regenerated."""
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO case_summaries(conversation_id, latest_turn_id, situation, "
                "open_items_json, last_contact, model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(conversation_id) DO UPDATE SET latest_turn_id = excluded.latest_turn_id, "
                "situation = excluded.situation, open_items_json = excluded.open_items_json, "
                "last_contact = excluded.last_contact, model = excluded.model, "
                "created_at = excluded.created_at",
                (
                    conversation_id, latest_turn_id, summary.get("situation", ""),
                    # Column kept NOT NULL and written empty; open_items is no longer
                    # produced or read (see get_case_summary).
                    "[]", summary.get("last_contact", ""),
                    summary.get("model"), utc_now(),
                ),
            )

    def get_customer_context(self, customer_id: str) -> dict | None:
        """The cached LLM-grouped customer record, or None. Callers compare record_hash
        against a fingerprint of the current record to decide whether it is still current."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM customer_context WHERE customer_id = ?", (customer_id,)
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        try:
            record["categories"] = json.loads(record.pop("categories_json") or "{}")
        except (ValueError, TypeError):
            record["categories"] = {}
        return record

    def save_customer_context(
        self, customer_id: str, record_hash: str, categories: dict, model: str | None
    ) -> None:
        """Upsert: one grouped record per customer, replaced whenever it is regenerated."""
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO customer_context(customer_id, record_hash, categories_json, "
                "model, created_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(customer_id) DO UPDATE SET record_hash = excluded.record_hash, "
                "categories_json = excluded.categories_json, model = excluded.model, "
                "created_at = excluded.created_at",
                (customer_id, record_hash, json_text(categories or {}), model, utc_now()),
            )

    def get_opportunity_evaluation(self, conversation_id: str) -> dict | None:
        """The last opportunity evaluation for a conversation, or None. Callers compare
        input_hash against a fingerprint of the current inputs to decide whether to re-run."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM opportunity_evaluations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_opportunity_evaluation(
        self, conversation_id: str, input_hash: str, suppressed: str | None
    ) -> None:
        """Upsert: one evaluation record per conversation, replaced whenever it re-runs."""
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO opportunity_evaluations(conversation_id, input_hash, suppressed, "
                "created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(conversation_id) DO UPDATE SET input_hash = excluded.input_hash, "
                "suppressed = excluded.suppressed, created_at = excluded.created_at",
                (conversation_id, input_hash, suppressed, utc_now()),
            )

    def create_ticket(self, ticket: Ticket) -> Ticket:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO tickets(ticket_id, conversation_id, customer_id, title, description, intent, priority, "
                "assigned_team, status, external_ticket_id, external_ticket_url, crm_sync_status, crm_sync_error, "
                "approval_status, escalation_reason, sla_due_at, priority_score, priority_breakdown_json, "
                "metadata_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket.ticket_id, ticket.conversation_id, ticket.customer_id, ticket.title, ticket.description,
                    ticket.intent, ticket.priority.value, ticket.assigned_team, ticket.status.value,
                    ticket.external_ticket_id, ticket.external_ticket_url, ticket.crm_sync_status,
                    ticket.crm_sync_error, ticket.approval_status, ticket.escalation_reason,
                    ticket.sla_due_at.isoformat() if ticket.sla_due_at else None,
                    ticket.priority_score, json_text(ticket.priority_breakdown), json_text(ticket.metadata),
                    ticket.created_at.isoformat(), ticket.updated_at.isoformat(),
                ),
            )
        return ticket

    def update_ticket(self, ticket_id: str, **values) -> dict | None:
        allowed = {
            "status", "priority", "external_ticket_id", "external_ticket_url", "crm_sync_status", "crm_sync_error",
            "approval_status", "escalation_reason", "sla_due_at", "priority_score", "priority_breakdown_json",
            "metadata_json", "description",
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
                "SELECT * FROM tickets WHERE conversation_id = ? AND status != 'closed' ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return self._ticket(row) if row else None

    def find_active_ticket_for_intent(self, conversation_id: str, intent: str) -> Ticket | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE conversation_id = ? AND intent = ? AND status != 'closed' "
                "ORDER BY created_at DESC LIMIT 1",
                (conversation_id, intent),
            ).fetchone()
        return self._ticket(row) if row else None

    def find_active_ticket_for_scope(self, conversation_id: str, intent: str, ticket_scope: str) -> Ticket | None:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE conversation_id = ? AND intent = ? AND status != 'closed' "
                "ORDER BY created_at DESC",
                (conversation_id, intent),
            ).fetchall()
        for row in rows:
            ticket = self._ticket(row)
            if ticket.metadata.get("ticket_scope") == ticket_scope:
                return ticket
        return None

    def list_active_tickets_for_intent(self, conversation_id: str, intent: str) -> list[Ticket]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE conversation_id = ? AND intent = ? AND status != 'closed' "
                "ORDER BY created_at DESC",
                (conversation_id, intent),
            ).fetchall()
        return [self._ticket(row) for row in rows]

    def list_active_tickets_for_conversation(self, conversation_id: str, limit: int = 5) -> list[Ticket]:
        """Open tickets for a conversation regardless of intent, newest first.

        The referee's candidate list used to be filtered by the INCOMING message's intent,
        which silently excluded the most common follow-up of all: "any update on my
        dispute?" classifies as ticket_status, so a transaction_dispute ticket was never a
        candidate and the referee was never even called. Relatedness is a judgement about
        the text, not about matching intent labels — so candidates are gathered by
        conversation and the referee decides.

        Bounded deliberately: each candidate costs prompt tokens and adds another chance to
        mis-match, so only the most recent few are offered.
        """
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE conversation_id = ? AND status != 'closed' "
                "ORDER BY created_at DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [self._ticket(row) for row in rows]

    def find_open_tickets_for_customer(self, customer_id: str, limit: int = 5) -> list[dict]:
        """Return all open (non-resolved) tickets for a customer across all channels."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE customer_id = ? AND status != 'closed' "
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

    def add_agent_assist_recommendation(
        self,
        conversation_id: str,
        customer_id: str,
        ticket_id: str | None,
        action_type: str,
        reason: str,
        confidence: float,
        priority: int = 0,
        metadata: dict | None = None,
    ) -> dict:
        recommendation_id = new_id("nba")
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO agent_assist_recommendations(recommendation_id, conversation_id, ticket_id, "
                "customer_id, action_type, reason, confidence, priority, metadata_json, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    recommendation_id, conversation_id, ticket_id, customer_id, action_type, reason,
                    confidence, priority, json_text(metadata), utc_now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM agent_assist_recommendations WHERE recommendation_id = ?", (recommendation_id,)
            ).fetchone()
        return self._json_fields(dict(row), "metadata_json")

    def list_agent_assist_recommendations(
        self,
        conversation_id: str | None = None,
        ticket_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        query = "SELECT * FROM agent_assist_recommendations WHERE 1=1"
        args: list = []
        if conversation_id:
            query += " AND conversation_id = ?"
            args.append(conversation_id)
        if ticket_id:
            query += " AND ticket_id = ?"
            args.append(ticket_id)
        if status:
            query += " AND status = ?"
            args.append(status)
        query += " ORDER BY confidence DESC, created_at DESC"
        with self.connection() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._json_fields(dict(row), "metadata_json") for row in rows]

    def get_agent_assist_recommendation(self, recommendation_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_assist_recommendations WHERE recommendation_id = ?", (recommendation_id,)
            ).fetchone()
        return self._json_fields(dict(row), "metadata_json") if row else None

    def update_agent_assist_recommendation(self, recommendation_id: str, status: str, actor: str) -> dict | None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE agent_assist_recommendations SET status = ?, decided_by = ?, decided_at = ? "
                "WHERE recommendation_id = ?",
                (status, actor, utc_now(), recommendation_id),
            )
            row = conn.execute(
                "SELECT * FROM agent_assist_recommendations WHERE recommendation_id = ?", (recommendation_id,)
            ).fetchone()
        return self._json_fields(dict(row), "metadata_json") if row else None

    # ── Human-in-the-loop reply drafts ────────────────────────────────────────
    def add_reply_draft(
        self,
        conversation_id: str,
        customer_id: str,
        channel: str,
        draft_text: str,
        ticket_id: str | None = None,
        inbound_turn_id: str | None = None,
        hold_reason: str = "",
        reason_code: str = "",
        channel_identifier: str | None = None,
        provider: str | None = None,
        retrieval_confidence: float | None = None,
        intent_confidence: float | None = None,
        offer_product: str | None = None,
    ) -> dict:
        draft_id = new_id("draft")
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO reply_drafts(draft_id, conversation_id, customer_id, ticket_id, channel, "
                "channel_identifier, provider, inbound_turn_id, draft_text, hold_reason, reason_code, "
                "retrieval_confidence, intent_confidence, offer_product, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    draft_id, conversation_id, customer_id, ticket_id, channel, channel_identifier,
                    provider, inbound_turn_id, draft_text, hold_reason, reason_code,
                    retrieval_confidence, intent_confidence, offer_product, utc_now(),
                ),
            )
            row = conn.execute("SELECT * FROM reply_drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        return dict(row)

    def list_reply_drafts(
        self, conversation_id: str | None = None, status: str | None = None
    ) -> list[dict]:
        query = "SELECT * FROM reply_drafts WHERE 1=1"
        args: list = []
        if conversation_id:
            query += " AND conversation_id = ?"
            args.append(conversation_id)
        if status:
            query += " AND status = ?"
            args.append(status)
        query += " ORDER BY created_at DESC"
        with self.connection() as conn:
            rows = conn.execute(query, args).fetchall()
        return [dict(row) for row in rows]

    def get_reply_draft(self, draft_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM reply_drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        return dict(row) if row else None

    def update_reply_draft(
        self, draft_id: str, status: str, actor: str, sent_text: str | None = None
    ) -> dict | None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE reply_drafts SET status = ?, decided_by = ?, decided_at = ?, "
                "sent_text = COALESCE(?, sent_text) WHERE draft_id = ?",
                (status, actor, utc_now(), sent_text, draft_id),
            )
            row = conn.execute("SELECT * FROM reply_drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        return dict(row) if row else None

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

    def add_llm_usage_event(self, event: dict) -> dict:
        event_id = event.get("event_id") or new_id("llm")
        created_at = event.get("created_at") or utc_now()
        values = {
            "event_id": event_id,
            "correlation_id": event.get("correlation_id"),
            "conversation_id": event.get("conversation_id"),
            "customer_id": event.get("customer_id"),
            "message_id": event.get("message_id"),
            "channel": event.get("channel"),
            "agent": event.get("agent"),
            "operation": event.get("operation") or "unknown",
            "provider": event.get("provider") or "unknown",
            "model": event.get("model") or "unknown",
            "model_version": event.get("model_version"),
            "llm_used": 1 if event.get("llm_used") else 0,
            "prompt_tokens": int(event.get("prompt_tokens") or 0),
            "completion_tokens": int(event.get("completion_tokens") or 0),
            "total_tokens": int(event.get("total_tokens") or 0),
            "estimated_cost_usd": float(event.get("estimated_cost_usd") or 0.0),
            "latency_ms": event.get("latency_ms"),
            "status": event.get("status") or "unknown",
            "error": event.get("error"),
            "intent": event.get("intent"),
            "resolution_level": event.get("resolution_level"),
            "ticket_id": event.get("ticket_id"),
            "retrieval_backend": event.get("retrieval_backend"),
            "metadata_json": json_text(event.get("metadata")),
            "created_at": created_at,
        }
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO llm_usage_events(
                    event_id, correlation_id, conversation_id, customer_id, message_id, channel,
                    agent, operation, provider, model, model_version, llm_used, prompt_tokens, completion_tokens,
                    total_tokens, estimated_cost_usd, latency_ms, status, error, intent,
                    resolution_level, ticket_id, retrieval_backend, metadata_json, created_at
                )
                VALUES (
                    :event_id, :correlation_id, :conversation_id, :customer_id, :message_id, :channel,
                    :agent, :operation, :provider, :model, :model_version, :llm_used, :prompt_tokens, :completion_tokens,
                    :total_tokens, :estimated_cost_usd, :latency_ms, :status, :error, :intent,
                    :resolution_level, :ticket_id, :retrieval_backend, :metadata_json, :created_at
                )
                """,
                values,
            )
        return self.get_llm_usage_event(event_id) or {}

    def get_llm_usage_event(self, event_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM llm_usage_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._llm_usage_dict(row) if row else None

    def list_llm_usage_events(self, limit: int = 100, correlation_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM llm_usage_events"
        args: tuple = ()
        if correlation_id:
            query += " WHERE correlation_id = ?"
            args = (correlation_id,)
        query += " ORDER BY created_at DESC LIMIT ?"
        args = (*args, max(1, min(int(limit or 100), 500)))
        with self.connection() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._llm_usage_dict(row) for row in rows]

    def get_llm_usage_summary(self, days: int = 7) -> dict:
        cutoff = None
        if days and days > 0:
            from datetime import timedelta

            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        where = "WHERE created_at >= ?" if cutoff else ""
        args: tuple = (cutoff,) if cutoff else ()
        with self.connection() as conn:
            totals = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS calls,
                    SUM(CASE WHEN llm_used = 1 THEN 1 ELSE 0 END) AS successful_calls,
                    SUM(prompt_tokens) AS prompt_tokens,
                    SUM(completion_tokens) AS completion_tokens,
                    SUM(total_tokens) AS total_tokens,
                    SUM(estimated_cost_usd) AS estimated_cost_usd,
                    AVG(latency_ms) AS avg_latency_ms
                FROM llm_usage_events
                {where}
                """,
                args,
            ).fetchone()

            by_operation = conn.execute(
                f"""
                SELECT operation, COUNT(*) AS calls, SUM(total_tokens) AS total_tokens,
                       SUM(estimated_cost_usd) AS estimated_cost_usd, AVG(latency_ms) AS avg_latency_ms
                FROM llm_usage_events
                {where}
                GROUP BY operation
                ORDER BY estimated_cost_usd DESC, total_tokens DESC
                """,
                args,
            ).fetchall()

            by_model = conn.execute(
                f"""
                SELECT model, COALESCE(model_version, 'unknown') AS model_version,
                       COUNT(*) AS calls, SUM(total_tokens) AS total_tokens,
                       SUM(estimated_cost_usd) AS estimated_cost_usd, AVG(latency_ms) AS avg_latency_ms,
                       -- Which pipeline steps run under this config. A version tag is a
                       -- hash, so this is the only thing that says what it is FOR.
                       GROUP_CONCAT(DISTINCT operation) AS operations,
                       MAX(metadata_json) AS _meta_sample
                FROM llm_usage_events
                {where}
                GROUP BY model, COALESCE(model_version, 'unknown')
                ORDER BY estimated_cost_usd DESC, total_tokens DESC
                """,
                args,
            ).fetchall()

            by_resolution_level = conn.execute(
                f"""
                SELECT COALESCE(resolution_level, 'unknown') AS resolution_level, COUNT(*) AS calls,
                       SUM(total_tokens) AS total_tokens, SUM(estimated_cost_usd) AS estimated_cost_usd
                FROM llm_usage_events
                {where}
                GROUP BY COALESCE(resolution_level, 'unknown')
                ORDER BY calls DESC
                """,
                args,
            ).fetchall()

            by_channel = conn.execute(
                f"""
                SELECT COALESCE(channel, 'unknown') AS channel, COUNT(*) AS calls,
                       SUM(total_tokens) AS total_tokens, SUM(estimated_cost_usd) AS estimated_cost_usd
                FROM llm_usage_events
                {where}
                GROUP BY COALESCE(channel, 'unknown')
                ORDER BY estimated_cost_usd DESC, total_tokens DESC
                """,
                args,
            ).fetchall()

            by_intent = conn.execute(
                f"""
                SELECT COALESCE(intent, 'unknown') AS intent, COUNT(*) AS calls,
                       SUM(total_tokens) AS total_tokens, SUM(estimated_cost_usd) AS estimated_cost_usd
                FROM llm_usage_events
                {where}
                GROUP BY COALESCE(intent, 'unknown')
                ORDER BY estimated_cost_usd DESC, total_tokens DESC
                LIMIT 10
                """,
                args,
            ).fetchall()

            # Hourly time-series per (model, version) — feeds the two side-by-side
            # cost-over-time / tokens-over-time line charts (one line per model+version).
            # created_at is stored UTC; bucket by IST (UTC+5:30) so the hour labels match
            # the operator's local clock. (India-only deployment — same assumption as the
            # WhatsApp +91 normalization.)
            time_series = conn.execute(
                f"""
                SELECT strftime('%Y-%m-%dT%H:00', created_at, '+5 hours', '+30 minutes') AS hour,
                       model,
                       COALESCE(model_version, 'unknown') AS model_version,
                       COUNT(*) AS calls,
                       SUM(total_tokens) AS total_tokens,
                       SUM(estimated_cost_usd) AS estimated_cost_usd
                FROM llm_usage_events
                {where}
                GROUP BY hour, model, COALESCE(model_version, 'unknown')
                ORDER BY hour
                """,
                args,
            ).fetchall()

        return {
            "window_days": days,
            "totals": {
                "calls": totals["calls"] or 0,
                "successful_calls": totals["successful_calls"] or 0,
                "prompt_tokens": totals["prompt_tokens"] or 0,
                "completion_tokens": totals["completion_tokens"] or 0,
                "total_tokens": totals["total_tokens"] or 0,
                "estimated_cost_usd": round(totals["estimated_cost_usd"] or 0.0, 6),
                "avg_latency_ms": round(totals["avg_latency_ms"] or 0.0, 2),
            },
            "by_operation": [self._usage_group(row) for row in by_operation],
            "by_model": [self._usage_group(row) for row in by_model],
            "by_channel": [self._usage_group(row) for row in by_channel],
            "by_intent": [self._usage_group(row) for row in by_intent],
            "by_resolution_level": [self._usage_group(row) for row in by_resolution_level],
            "time_series": [self._usage_group(row) for row in time_series],
        }

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
    def _usage_group(row: sqlite3.Row) -> dict:
        value = dict(row)
        if "estimated_cost_usd" in value:
            value["estimated_cost_usd"] = round(value["estimated_cost_usd"] or 0.0, 6)
        if "avg_latency_ms" in value:
            value["avg_latency_ms"] = round(value["avg_latency_ms"] or 0.0, 2)
        for key in ("calls", "total_tokens"):
            if key in value:
                value[key] = value[key] or 0
        # Decode the config behind a version tag (for the "Cost/Latency by model / version" panels).
        # All rows in a (model, version) group share the same config, so any sample suffices.
        if "_meta_sample" in value:
            sample = value.pop("_meta_sample")
            try:
                value["model_config"] = (json.loads(sample) or {}).get("model_config")
            except (TypeError, ValueError):
                value["model_config"] = None
        return value

    @staticmethod
    def _llm_usage_dict(row: sqlite3.Row) -> dict:
        value = SQLiteCXRepository._json_fields(dict(row), "metadata_json")
        value["llm_used"] = bool(value.get("llm_used"))
        value["metadata"] = value.get("metadata") or {}
        return value

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
        if "priority_breakdown_json" in value:
            value["priority_breakdown"] = json.loads(value.pop("priority_breakdown_json") or "{}")
        return value
