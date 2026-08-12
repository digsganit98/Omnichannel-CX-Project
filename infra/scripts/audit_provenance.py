"""Audit the /provenance endpoint against EVERY outbound turn and flag disagreements.

The point is that the user should not be the one finding these. This calls the real
endpoint for every reply in the database and applies cheap consistency checks that catch
the class of bug found by hand:

  MISMATCH   the reply quotes a rupee figure / date that looks like account data, but the
             panel says the answer came from the knowledge base
  UNGROUNDED the panel cites a KB passage whose topic shares no keyword with the reply
  ERROR      the endpoint failed for this turn

Nothing here needs an LLM; it is string evidence only, so it can run on every turn.

Usage:
    python infra/scripts/audit_provenance.py            # reads ADMIN_API_KEY from .env
    python infra/scripts/audit_provenance.py <key>
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

BASE = os.environ.get("CX_API_BASE", "http://localhost:8888")


def _admin_key() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    env = Path(__file__).resolve().parents[2] / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("ADMIN_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("ADMIN_API_KEY not found - pass it as an argument")


KEY = _admin_key()


def get(path):
    req = urllib.request.Request(BASE + path, headers={"x-admin-key": KEY})
    return json.loads(urllib.request.urlopen(req).read())


# Signals that a reply contains customer-specific data rather than general guidance.
ACCOUNT_SIGNAL = re.compile(
    r"(Rs\.?\s?[\d,]{4,}|₹\s?[\d,]{4,}|\b\d{4}-\d{2}-\d{2}\b|"
    r"\b(?:CC|FD|LN|POL|CLM)\d{4,}\b|\bxxxx\d+\b|\b\d{10,}\b)", re.I)
STOP = set("the a an of to and or is are was were for with your you my our this that it "
           "on in at by be as will can may from please thank hi hello dear we us".split())


def words(t):
    return {w for w in re.findall(r"[a-z]{4,}", (t or "").lower()) if w not in STOP}


# A holding message is not an answer, so comparing a citation against it is meaningless —
# the first run flagged 9 of these as "ungrounded" and inflated the real count.
HOLDING = "support agent will help you with this shortly"

rows, errors, skipped = [], 0, 0
convs = get("/admin/conversations")
for c in convs:
    detail = get("/admin/conversations/" + c["conversation_id"])
    for t in detail.get("turns") or []:
        if t.get("direction") != "outbound" or not (t.get("text") or "").strip():
            continue
        if (t.get("text") or "").strip().lower().startswith(HOLDING):
            skipped += 1
            continue
        tid = t["turn_id"]
        try:
            p = get(f"/admin/conversations/turns/{tid}/provenance")
        except Exception as exc:
            rows.append(("ERROR", tid, str(exc)[:60], "", ""))
            errors += 1
            continue

        text = t.get("text") or ""
        has_acct = bool(ACCOUNT_SIGNAL.search(text))
        src = p.get("source")
        cites = p.get("citations") or []

        flag, note = "ok", ""
        if src == "kb" and has_acct:
            flag = "MISMATCH"
            note = "reply contains account-specific data but panel says KB"
        elif src == "kb" and cites:
            overlap = words(text) & words(cites[0].get("text"))
            if not overlap:
                flag = "UNGROUNDED"
                note = "cited passage shares no keyword with the reply"
        rows.append((flag, tid, p.get("intent") or "-", src or "-", note))

bad = [r for r in rows if r[0] != "ok"]
print(f"audited {len(rows)} replies across {len(convs)} conversations\n")
w = max([len(r[2]) for r in rows] + [10])
for flag, tid, intent, src, note in rows:
    if flag != "ok":
        print(f"  {flag:11} {tid:22} {intent:{w}} src={src:6} {note}")
print(f"\n  ok         {len(rows)-len(bad)}")
print(f"  flagged    {len(bad)}   (errors: {errors})")
if bad:
    print("\nBreakdown:")
    for k in ("ERROR", "MISMATCH", "UNGROUNDED"):
        n = sum(1 for r in bad if r[0] == k)
        if n:
            print(f"  {k:11} {n}")
