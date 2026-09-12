"""Seed the Service Desk routing roster.

WHY THIS EXISTS
---------------
A ticket has to be owned by someone. With a single account every ticket belongs to the
one person looking at the board, so there is no routing to see: no load to balance, no
one to reassign to, no capacity to be at. This seeds a realistic bench of agents across
the teams that assign_team() actually produces, so the board shows real distribution.

These are ROWS, not logins. They are given an unusable password hash on purpose - nobody
signs in as them.

A REAL ACCOUNT IS DELIBERATELY LEFT TEAM-LESS
---------------------------------------------
Seeded agents belong to a team; the person signed in does NOT, and this is the whole
design rather than an omission.

The team is decided by the AI from the customer's question - assign_team() maps the
classified intent, so a UPI dispute becomes fraud_and_disputes and a card question
becomes card_services. Nobody can know which team a ticket will land in before the
customer has asked. Giving the signed-in operator a fixed team would therefore lock them
out of most of their own tickets: they would have to guess their team in advance and only
ask matching questions, or assign to a seeded agent they cannot then act as.

So `team IS NULL` carries a meaning: this is an operator, not a queue member. They can
take ANY ticket in ANY team, and they have no capacity ceiling to be "full" against.
Every real account behaves identically - there is no default or special account, so a
teammate or a fresh signup during a demo gets exactly the same board.

SAFETY
------
Idempotent and additive. It never updates, re-teams or deletes an existing admin_users
row, so a real account's password, email and team cannot be touched by re-running it. It
only INSERTs seeded agents that are absent.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone

# Teams are not invented here - these are exactly the values assign_team() emits, via
# INTENT_TO_TEAM in shared/constants/intents.py. A team that no intent maps to would
# never receive a ticket and would sit empty on the board forever.
AGENTS = [
    # (username,        email,                         team,                   capacity)
    ("Priya_Nair",      "priya.nair@example.com",      "fraud_and_disputes",    8),
    ("Rahul_Menon",     "rahul.menon@example.com",     "fraud_and_disputes",    8),
    ("Kavya_Iyer",      "kavya.iyer@example.com",      "claims",                8),
    ("Arjun_Das",       "arjun.das@example.com",       "claims",                6),
    ("Meera_Pillai",    "meera.pillai@example.com",    "retail_banking",        8),
    ("Vikram_Shetty",   "vikram.shetty@example.com",   "payments",              8),
    ("Ananya_Bose",     "ananya.bose@example.com",     "card_services",         8),
    ("Rohit_Kulkarni",  "rohit.kulkarni@example.com",  "loans",                 8),
    ("Divya_Raman",     "divya.raman@example.com",     "compliance",            6),
    ("Sanjay_Gupta",    "sanjay.gupta@example.com",    "collections",           6),
    ("Neha_Joshi",      "neha.joshi@example.com",      "insurance_operations",  8),
    ("Farhan_Qureshi",  "farhan.qureshi@example.com",  "customer_care",         8),
]

# Not a hash of anything - pbkdf2 verification splits on ':' and compares hex, so this
# can never match a password. These accounts are not sign-in-able by construction.
UNUSABLE_PASSWORD = "seeded:no-login"


def seed(db_path: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(admin_users)")}
        if "team" not in cols or "capacity" not in cols:
            print("ERROR: migration 019 has not been applied to this database.", file=sys.stderr)
            return 1

        existing = {r["username"] for r in conn.execute("SELECT username FROM admin_users")}

        inserted = 0
        for username, email, team, capacity in AGENTS:
            if username in existing:
                continue
            conn.execute(
                "INSERT INTO admin_users(username, email, password_hash, created_at, team, capacity) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (username, email, UNUSABLE_PASSWORD, now, team, capacity),
            )
            inserted += 1

        conn.commit()

        # Real accounts are reported separately so it is obvious they were left alone -
        # a team-less row here is correct, not a row the seed failed to fill in.
        operators = [
            r["username"]
            for r in conn.execute("SELECT username FROM admin_users WHERE team IS NULL ORDER BY username")
        ]

        print(f"agents inserted: {inserted}")
        print("\nseeded agents (assignable within their team):")
        for r in conn.execute(
            "SELECT username, team, capacity FROM admin_users WHERE team IS NOT NULL ORDER BY team, username"
        ):
            print(f"  {r['username']:18} {r['team']:22} cap={r['capacity']}")
        print("\noperators (no team - can take ANY ticket, no capacity ceiling):")
        for name in operators:
            print(f"  {name}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DB_PATH", "/app/data/cx_phase1.db")
    raise SystemExit(seed(path))
