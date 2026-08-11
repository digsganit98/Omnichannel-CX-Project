"""Backfill :Ticket nodes into Neo4j for tickets that predate the id-namespace fix.

Historic tickets were written with the SQLite ``cust_…`` customer id, which never matched
``MATCH (c:Customer {customer_id: 'CRN…'})`` — so ``upsert_ticket_node`` silently created
nothing. The pipeline fix resolves the sender to the real ``CRN…`` for NEW tickets; this
script does the same resolution for tickets already on disk.

Tickets whose customer resolves to no graph Customer (unverified senders) are SKIPPED by
design — the same rule that stops phantom nodes.

Usage:
    python infra/scripts/backfill_ticket_nodes.py            # dry run (default)
    python infra/scripts/backfill_ticket_nodes.py --apply    # write
"""

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.neo4j_service.client import Neo4jClient  # noqa: E402
from services.neo4j_service.queries import get_customer_by_identifier  # noqa: E402
from services.neo4j_service.writer import upsert_ticket_node  # noqa: E402

DB_PATH = os.environ.get("DATABASE_PATH", "/app/data/cx_phase1.db")


def _identifiers_for(conn, customer_id: str) -> list[str]:
    """Phone/email identifiers for a SQLite customer, best-first."""
    out: list[str] = []
    row = conn.execute(
        "SELECT metadata_json FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    if row and row[0]:
        try:
            meta = json.loads(row[0])
            for key in ("linked_email", "email", "phone"):
                if meta.get(key):
                    out.append(str(meta[key]))
        except (ValueError, TypeError):
            pass
    for (ident,) in conn.execute(
        "SELECT identifier FROM channel_identities WHERE customer_id = ?", (customer_id,)
    ):
        if ident:
            out.append(str(ident))
    seen: set[str] = set()
    return [i for i in out if not (i in seen or seen.add(i))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to Neo4j (default: dry run)")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    client = Neo4jClient()

    before = client.query("MATCH (t:Ticket) RETURN count(t) AS n")[0]["n"]
    print(f"DB={DB_PATH}  mode={'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Ticket nodes before: {before}\n")

    tickets = list(conn.execute(
        "SELECT ticket_id, customer_id, intent, priority, status FROM tickets ORDER BY created_at"
    ))
    resolved_cache: dict[str, str | None] = {}
    planned, skipped = [], []

    for t in tickets:
        cust = t["customer_id"]
        if cust not in resolved_cache:
            crn = None
            for ident in _identifiers_for(conn, cust):
                found = get_customer_by_identifier(client, ident)
                if found and found.get("customer_id"):
                    crn = found["customer_id"]
                    break
            resolved_cache[cust] = crn
        crn = resolved_cache[cust]
        if crn:
            planned.append((t, crn))
        else:
            skipped.append((t, cust))

    print(f"WILL WRITE ({len(planned)}):")
    for t, crn in planned:
        print(f"  {t['ticket_id']}  {t['customer_id']} -> {crn}  [{t['intent']}/{t['status']}]")
    print(f"\nWILL SKIP — no graph customer ({len(skipped)}):")
    for t, cust in skipped:
        print(f"  {t['ticket_id']}  {cust}  [{t['intent']}/{t['status']}]")

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply to write.")
        client.close()
        conn.close()
        return 0

    print()
    for t, crn in planned:
        upsert_ticket_node(
            client,
            ticket_id=t["ticket_id"],
            customer_id=crn,
            intent=t["intent"] or "",
            priority=str(t["priority"] or ""),
            status=t["status"] or "",
        )
        print(f"  wrote {t['ticket_id']} -> {crn}")

    after = client.query("MATCH (t:Ticket) RETURN count(t) AS n")[0]["n"]
    rels = client.query("MATCH ()-[r:HAS_TICKET]->() RETURN count(r) AS n")[0]["n"]
    print(f"\nTicket nodes after: {after} (was {before})   HAS_TICKET: {rels}")

    client.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
