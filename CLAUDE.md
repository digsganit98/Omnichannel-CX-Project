# Omnichannel-CX-Project — read this before running anything

> **This file is about the LOCAL machine only.** Every command, port and volume name below
> is for the laptop. **EC2 is a different machine with different commands** — for anything
> on it, stop and read `docs/rules_to_follow/ec2-operations.md` first. Do not adapt
> instructions from this file to that box.

This file exists because a session went looking for how to start the app, opened a
disaster-recovery runbook (since deleted) instead of the README, and proposed destroying every conversation,
ticket and login to fix a stack that was merely stopped. The facts below were already written
down somewhere and still got missed.

## Starting the app

**The API is on host port 8888** (`"8888:8000"` in compose). Older docs saying 8000 are wrong.
The UI is at **http://localhost:8888/admin-ui**.

```bash
docker compose up -d      # normal start - keeps all data
docker compose down       # stop - keeps all data
```

`README.md` § "Running it locally, start to finish" is the startup document. Read it first.

**A Python change needs a rebuild, not a restart.** Only `apps/admin-ui` is bind-mounted;
everything else is baked into the image, so `restart` silently runs the old code:

```bash
docker compose build api && docker compose up -d api
```

**`docker compose restart` also does not re-read `.env`.** Environment is fixed when a
container is *created*. `RAG_BACKEND=neo4j` was once set, the container restarted, and the
app still reported `opensearch` with a clean log and no error anywhere. Changed `.env` →
`docker compose up -d api`, which recreates it.

## What is actually running

| service | why |
|---|---|
| `api` | FastAPI backend + both UIs, port 8888 |
| `neo4j` | the graph **and** the KB vector store — `RAG_BACKEND=neo4j` |
| `ngrok` | **profile-gated, do not start** — see below |

`opensearch` and `ollama` are **commented out of compose** (2026-09-16). Nothing read either:
`RAG_BACKEND` defaults to `neo4j` in code, and `OLLAMA_ENABLED=false` with a 32 kB volume
meaning no model was ever pulled. The compose comments explain how to restore each.
**Do not copy the opensearch removal to EC2** — it is kept running there as the rollback,
because re-pulling 1.34 GB onto a 94%-full shared disk may fail.

## Never, without being asked

- **Never start ngrok.** It sits behind `profiles: ["tunnel"]`. Free-tier ngrok allows ONE
  online session and EC2 holds the team domain, so a laptop starting it either dies with
  ERR_NGROK_334 or **steals the tunnel and starts receiving real customers' WhatsApp
  messages** while the live demo goes silent.
- **Never send real outbound** (email or WhatsApp) to test plumbing. Use the minimal step and
  throwaway targets.
- **Never `git add -A`.** `docs/design-options/` is gitignored and gets staged anyway.
- **Never `docker image prune` or `docker system prune --volumes` on EC2.** ~42 containers
  across ~30 projects share that box. A "safe" prune there once deleted 5.94 GB of another
  team's images.
- **Never regenerate `data/bfsi.xlsx`** — the generator is not reproducible (117 cells differ
  on an unmodified run).

## Wiping data — a fresh start

`docker compose down -v` and `docker volume rm` are **disaster recovery, not a routine
start**. They destroy all conversations, tickets, drafts, audit events and **the portal/admin
logins**. Containers showing `Exited (255)` only mean the Docker daemon stopped — the data is
intact and a plain `up -d` brings it back.

If a full wipe is genuinely wanted, the whole procedure is:

```bash
docker compose down
docker volume rm omnichannel-cx-project_cx-data omnichannel-cx-project_neo4j-data
docker compose up -d --build
```

Wipe **only those two volumes**; `huggingface-cache` holds the embedding model and re-pulling
it is slow for nothing. `_seed_neo4j()` reseeds the 5 BFSI customers from `data/bfsi.xlsx` on
boot, but **only when the graph is empty** — wiping `neo4j-data` is what triggers it. Verified
2026-09-16: the seed files ship inside the image (`COPY . .` carries `data/`; only `*.db` is
excluded), so there is nothing to back up first.

**KB indexing is NOT automatic.** After the wipe:

```
POST /admin/rag/index?recreate=true     # expect indexed 14/14, errors 0
POST /admin/rag/link-kb-graph           # expect holdings_linked: 123
```
Read the key from the container (`docker compose exec -T api printenv ADMIN_API_KEY`) rather
than the file. Note `curl` is **not installed** in the api image — use `python -c` with
`urllib`. Then verify `Customer 5`, `KBChunk 14`, `Concept 18`, conversations 0.

**A wipe makes ZERO Groq calls** — the reseed uses `openpyxl` and a local SentenceTransformer.
It costs no quota. What burns quota is running test conversations afterwards.

**Your login does not come back.** `customer_users` and `admin_users` live in `cx-data`, so the
first sign-in after a wipe fails with "Invalid user ID or password" — that looks like a broken
app and is not. Sign up again at `/admin-ui`, and the email or phone **must match a seeded
record exactly** or identity resolution treats it as an unregistered customer (Fix 1):

| Customer | Email | Phone |
|---|---|---|
| Sayantini Sarkar | `sayantini.s.55@gmail.com` | 7890864700 |
| Sireesha | `s.sireesha28092004@gmail.com` | 9398314492 |
| Digvijay Yadav | `digvijayyadav48@gmail.com` | 7700920746 |
| Hirithi Nandha | `hirithi.nandha@gmail.com` | 9150697784 |
| Fathima Devasahayam | `fathimawork511@gmail.com` | 7538870992 |

The admin login needs recreating the same way.

**On a clean shell (Windows):** `docker compose` ranks **shell env above `.env`**. If
`WHATSAPP_ACCESS_TOKEN` or `NGROK_DOMAIN` are set in the PowerShell session, they silently
shadow `.env`. Check with `Test-Path Env:WHATSAPP_ACCESS_TOKEN` — don't echo the value.

Two boot lines that look like failures and are not: `label Customer does not exist` (the seed
checking an empty graph) and a 404 on an old `conv_*` id (someone's open browser tab).

## When the AI goes quiet — check Groq quota first

An exhausted Groq daily cap **does not fail loudly**: replies come back empty and the caller
may print raw retrieved records to the customer. It looks exactly like broken AI code, and
once cost a whole debugging session. Quota is a **rolling 24h window**, not a midnight reset,
and a second key on the same org shares it.

```bash
docker compose exec -T api python -c "import os,groq; c=groq.Groq(api_key=os.environ['GROQ_API_KEY']); c.chat.completions.create(model=os.environ['GROQ_MODEL'],messages=[{'role':'user','content':'ping'}],max_tokens=1); print('GROQ OK')"
```
`429 ... tokens per day (TPD)` → exhausted. `401` → bad key. This is the **one** deliberate
real LLM call worth making; `max_tokens=1` keeps it negligible. Do not loop it — verify
everything else with reads. Local spend is at `/admin/llm-observability/summary?days=1`, but
after a wipe that table is empty and shows `0`, which means "this stack hasn't spent yet," not
"quota is full."

## ⛔ EC2 — stop and read the other file

**Nothing in this document applies to EC2.** Different port, different compose file, no git,
and a disk shared with ~30 other teams. Every EC2 procedure — deploying, restarting, wiping,
what must never be run there — lives in **`docs/rules_to_follow/ec2-operations.md`**. Read it
before touching that box; do not adapt anything from here.

That file is **updated only with the user's explicit permission.**

## Working style the user has asked for, repeatedly

- **Read the existing code and docs before proposing anything.** Most "new" problems here are
  already handled somewhere; search first.
- **Measure, never estimate.** Every intuited number in this project has been wrong.
- **Verify the end state, not the edit.** Check the running system, not the file just written —
  and confirm the check could actually detect failure. Several "verified" claims came from
  probes that could not have caught the bug (curl on the wrong port, a cache token never
  bumped, a probe reading the wrong dict key).
- **Lead with the simplest option.** Offer the smallest operational fix first.
- **Reuse the existing pattern and styling.** Do not reinvent a component that exists.
- **Answer first, in headed sections and lists** — not long prose.
- **Get approval before state-changing actions**, and once the user reaffirms a request, stop
  re-litigating it and do it.
