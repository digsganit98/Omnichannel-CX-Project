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
    def update_conversation_summary(self, conversation_id: str, summary: str) -> None: ...
    def create_ticket(self, ticket: Ticket) -> Ticket: ...
    def find_active_ticket(self, conversation_id: str) -> Ticket | None: ...
    def list_tickets(self) -> list[dict]: ...
    def get_ticket(self, ticket_id: str) -> dict | None: ...
    def add_retrieval_evidence(self, turn_id: str, contexts: list[dict]) -> None: ...
    def list_retrieval_evidence(self, turn_id: str | None = None) -> list[dict]: ...
    def add_audit_event(self, event_type: str, correlation_id: str, **values) -> None: ...
    def list_audit_events(self, correlation_id: str | None = None) -> list[dict]: ...
    def get_conversation(self, conversation_id: str) -> dict | None: ...
    def list_conversations(self) -> list[dict]: ...


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
        migration = Path(__file__).parent / "migrations" / "001_phase1.sql"
        with self.connection() as conn:
            conn.executescript(migration.read_text(encoding="utf-8"))

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
        identifiers = [(message.channel.value, message.channel_identifier)]
        linked_email = message.metadata.get("linked_email")
        linked_phone = message.metadata.get("linked_phone")
        if linked_email:
            identifiers.append((Channel.EMAIL.value, str(linked_email).strip().lower()))
        if linked_phone:
            identifiers.append((Channel.WHATSAPP.value, str(linked_phone).strip().lstrip("+")))

        with self.connection() as conn:
            customer_id = None
            for channel, identifier in identifiers:
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
                conn.execute(
                    "UPDATE customers SET display_name = COALESCE(?, display_name), updated_at = ? WHERE customer_id = ?",
                    (message.display_name, now, customer_id),
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
                "SELECT * FROM conversations WHERE customer_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
                (customer_id,),
            ).fetchone()
            if not row:
                now = utc_now()
                conversation_id = new_id("conv")
                conn.execute(
                    "INSERT INTO conversations(conversation_id, customer_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (conversation_id, customer_id, now, now),
                )
                row = conn.execute(
                    "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
                ).fetchone()
        return dict(row)

    def list_recent_turns(self, conversation_id: str, limit: int = 8) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [self._turn_dict(row) for row in reversed(rows)]

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
                "assigned_team, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket.ticket_id, ticket.conversation_id, ticket.customer_id, ticket.title, ticket.description,
                    ticket.intent, ticket.priority.value, ticket.assigned_team, ticket.status.value,
                    ticket.created_at.isoformat(), ticket.updated_at.isoformat(),
                ),
            )
        return ticket

    def find_active_ticket(self, conversation_id: str) -> Ticket | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE conversation_id = ? AND status != 'resolved' ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return self._ticket(row) if row else None

    def list_tickets(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_ticket(self, ticket_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
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
            rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _json_fields(value: dict, *fields: str) -> dict:
        for field in fields:
            value[field.removesuffix("_json")] = json.loads(value.pop(field) or "{}")
        return value

    def _turn_dict(self, row: sqlite3.Row) -> dict:
        return self._json_fields(dict(row), "metadata_json")

    @staticmethod
    def _ticket(row: sqlite3.Row) -> Ticket:
        value = dict(row)
        value["priority"] = TicketPriority(value["priority"])
        value["status"] = TicketStatus(value["status"])
        return Ticket(**value)
