# Fresh-Start Runbook — Full Data Wipe + Real WhatsApp

Repeatable procedure to tear the stack down to a **clean slate** (empty inbox, reseeded BFSI
customers, rebuilt KB) and bring it back up for a **real-WhatsApp** demo, with verification at
every step.

Every command below is verified against this project's actual `docker-compose.yml`, `apps/api/main.py`,
and route files (not the stale README). All paths assume the project root
`Omnichannel-CX-Project`.

> **Key facts that shape this runbook**
> - **API host port is `8888`** (`"8888:8000"` in compose). All URLs below use `:8888`.
> - **Neo4j auto-reseeds on API startup** — `apps/api/main.py::_seed_neo4j()` loads `data/bfsi.xlsx`
>   **only when the graph is empty** (`MATCH (c:Customer) RETURN count(c)` == 0). So wiping
>   `neo4j-data` is what triggers the reseed; no manual seed command is normally needed.
> - **KB indexing is NOT automatic** — must be triggered by an admin endpoint after wiping
>   `opensearch-data`.
> - **Two recurring traps** (both cost a live demo before): an **expired WhatsApp token** and the
>   **PowerShell env-var precedence** trap (shell env shadows `.env`). Both are handled below.

---

## The 5 Docker volumes — what to keep vs wipe

Exact names (project prefix `omnichannel-cx-project_`):

| Volume | Holds | Fresh wipe? |
|---|---|---|
| `omnichannel-cx-project_cx-data` | SQLite: conversations, tickets, drafts, audit | **WIPE** |
| `omnichannel-cx-project_neo4j-data` | BFSI customers (graph) | **WIPE** → triggers auto-reseed |
| `omnichannel-cx-project_opensearch-data` | RAG / KB vector index | **WIPE** → needs re-index |
| `omnichannel-cx-project_ollama-data` | Pulled LLM model (GBs) | **KEEP** (else re-download) |
| `omnichannel-cx-project_huggingface-cache` | Embedding model | **KEEP** (else re-download) |

> Keeping the two model volumes is what makes a fresh start fast (no multi-GB re-pull).

---

## Steps

### ① Fresh WhatsApp token in `.env` (do this FIRST)
Real WhatsApp outbound calls Meta's Graph API and **fails with 401 the moment the token expires**.
Temporary tokens (Graph API Explorer) expire in hours — that has broken the demo 3× already.

- Preferred: generate a **System User token** (Meta Business Settings → System Users) — it does
  **not** expire. This is the permanent fix to the recurring 401.
- Put it in `.env` as `WHATSAPP_ACCESS_TOKEN=...`.
- (Do not rely on the previous token — assume it is expired.)

Verification of the token happens in step ⑧ (via Meta `debug_token`), after the container loads it.

### ② Stop the stack
Containers must be down before their volumes can be removed.
```bash
docker compose down
```
Verify: `docker compose ps` shows nothing running.

### ③ Wipe the 3 data volumes (IRREVERSIBLE)
```bash
docker volume rm omnichannel-cx-project_cx-data omnichannel-cx-project_neo4j-data omnichannel-cx-project_opensearch-data
```
> Permanently deletes all conversations, tickets, drafts, audit events, and the KB index. The 5 BFSI
> customers are regenerated from `data/bfsi.xlsx` on next boot. **No undo.**

Verify the two model volumes survive:
```bash
docker volume ls --format '{{.Name}}' | grep -i omnichannel
# expect: huggingface-cache and ollama-data still present; the 3 wiped ones gone (recreated empty on up)
```

### ④ ⚠️ Open a CLEAN shell (PowerShell env-var precedence trap)
`docker compose` ranks **shell env > `.env`**. If `WHATSAPP_ACCESS_TOKEN` or `NGROK_DOMAIN` are
exported in the current PowerShell session, they silently shadow your new `.env` values.

In the shell you will run `up` from:
```powershell
echo $env:WHATSAPP_ACCESS_TOKEN   # must be empty
echo $env:NGROK_DOMAIN            # must be empty
```
If either prints a value, open a fresh PowerShell window (or `Remove-Item Env:WHATSAPP_ACCESS_TOKEN`).

### ⑤ Bring the stack up
```bash
docker compose up -d
```
- No `--build` needed unless backend code changed (current image already has all committed fixes).
- On boot, `_seed_neo4j()` reseeds the 5 BFSI customers into the now-empty graph.

Verify containers healthy:
```bash
docker compose ps        # all services "running"/"healthy"
```

### ⑥ Recreate ngrok + point Meta webhook at it (real WhatsApp only)
The ngrok `--url` is interpolated at container-create time and honors the same shell>`.env`
precedence. From the clean shell:
```bash
docker compose up -d --force-recreate ngrok
```
- Current domain in `.env`: `https://tactical-dribble-booting.ngrok-free.dev` (confirm it came up on
  this in `docker compose logs ngrok`).
- In Meta App dashboard, set the WhatsApp webhook callback URL to:
  `https://<ngrok-domain>/integrations/whatsapp/webhook`
  (the production webhook validates `x-hub-signature-256` with `WHATSAPP_APP_SECRET`).

### ⑦ Re-index the knowledge base (opensearch was wiped)
```powershell
$H = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Method Post -Headers $H "http://localhost:8888/admin/rag/index?recreate=true"
```
Expect a JSON result with `indexed` > 0 and `errors: 0`.

### ⑧ Recreate the portal / admin logins (they were in the wiped SQLite volume)

**The 5 BFSI customers come back automatically; YOUR LOGIN DOES NOT.** `customer_users` and
`admin_users` live in `cx-data`, so step ③ deletes them. The first sign-in after a wipe fails with
"Invalid user ID or password", which looks like a broken app and is not.

Sign up again on the portal, and **match the seeded customer's email or phone exactly** — identity
resolution links a portal signup to the BFSI record on those fields (Fix 1). A mismatch is treated
as an unregistered customer and rejected.

| Customer | Email | Phone |
|---|---|---|
| Sayantini Sarkar | `sayantini.s.55@gmail.com` | 7890864700 |
| Sireesha | `s.sireesha28092004@gmail.com` | 9398314492 |
| Digvijay Yadav | `digvijayyadav48@gmail.com` | 7700920746 |
| Hirithi Nandha | `hirithi.nandha@gmail.com` | 9150697784 |
| Fathima Devasahayam | `fathimawork511@gmail.com` | 7538870992 |

The admin login needs recreating the same way.

### ⑨ Check the model has daily quota left

A wipe does not reset Groq's daily token cap, and an exhausted model does not fail loudly: the
reply comes back empty and the caller prints the raw retrieved records to the customer. Before a
run, confirm the model in `GROQ_MODEL` still answers:

```
docker exec omnichannel-cx-project-api-1 python -c "import os; from groq import Groq; print(Groq(api_key=os.getenv('GROQ_API_KEY')).chat.completions.create(model=os.getenv('GROQ_MODEL'),messages=[{'role':'user','content':'hi'}],max_tokens=1).choices[0].message.content is not None)"
```

A 429 mentioning `tokens per day (TPD)` means switch `GROQ_MODEL` to another model — each has its
own 200K/day — and `docker compose up -d api`.

---

## ⑧ Verification checklist — verify EVERY external dependency (all read-only)

The demo relies on **seven** external services. Any one can silently break a "fresh" start and it
often looks like a code bug (Session 8: an exhausted Groq quota looked exactly like broken AI).
Verify all of them before demoing. Set the header once:
`$H = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }`

**Dependency map (what breaks what):**

| # | Dependency | If it's down | Check |
|---|---|---|---|
| a | API process | nothing works | `/health` |
| b | **Groq** (cloud LLM) | **every AI reply degrades / dumps KB** | `/admin/llm-observability/summary` + key probe |
| c | **Ollama** (local LLM) | intent/classification fails | `/admin/orchestration/ai-runtime` |
| d | **WhatsApp/Meta token** | outbound 401, phone gets nothing | Meta `debug_token` |
| e | **ngrok** | Meta can't reach the webhook (no inbound) | `docker compose logs ngrok` |
| f | **Neo4j** | no customer data / no reseed | `/admin/neo4j/status` |
| g | **OpenSearch/KB** | RAG has no knowledge | `/admin/rag/health` |
| + | SMTP / IMAP (email) | email send/receive fails | `/admin/email/status`, `/admin/email-inbox/status` |
| + | CRM / Jira | tickets don't sync (non-fatal) | `/admin/crm/status` |

### a. API healthy
```powershell
Invoke-RestMethod "http://localhost:8888/health"
```

### b. Groq — key valid AND quota left today  ⚠️ THE SESSION-8 TRAP
Two separate failure modes: a **bad key**, and a **valid key with 0 tokens left** (the 500K/day
rolling-window cap). The second is what silently wrecked the demo — every AI call 429s at once.

**b1 — local usage summary (no quota burned):**
```powershell
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/llm-observability/summary?days=1"
```
> ⚠️ **Honest limitation:** after wiping `cx-data`, the `llm_usage_events` table is empty, so this
> shows `0` spent by *this stack* — it does **not** report your Groq *account's* remaining quota
> (that lives server-side at Groq, rolling 24h). Empty here only means "this fresh stack hasn't
> spent yet," not "quota is full." Use it to *watch spend accumulate* during rehearsal (watch
> `opportunity_generation` — the heaviest per-message cost), and to spot 429 errors in the events
> feed: `/admin/llm-observability/events`.

**b2 — is the key even valid? (one tiny probe — costs a few tokens, acceptable once):**
```bash
docker exec omnichannel-cx-project-api-1 python -c "import os,groq; c=groq.Groq(api_key=os.environ['GROQ_API_KEY']); r=c.chat.completions.create(model=os.environ.get('GROQ_MODEL','llama-3.1-8b-instant'),messages=[{'role':'user','content':'ping'}],max_tokens=1); print('GROQ OK — key valid, quota available')"
```
- Prints `GROQ OK` → key valid and quota available right now.
- `429 ... tokens per day (TPD)` → **quota exhausted** — wait for the rolling window to roll off, or
  swap to a key on a *different* Groq account (a second key on the same org shares the 500K).
- `401 / invalid api key` → bad `GROQ_API_KEY` in `.env`.
> This is the ONE deliberate real LLM call in the checklist. `max_tokens=1` keeps it ~negligible.
> Do not loop it. (Rule: preserve Groq quota — verify with reads elsewhere, one probe here only.)

### c. Ollama — reachable + model installed
```powershell
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/orchestration/ai-runtime"
# expect llm.reachable: true, model_installed: true
```
If the model is missing (only when `ollama-data` was also wiped): `docker compose --profile setup run --rm ollama-pull`

### d. WhatsApp token valid + expiry (the other trap-catcher)
```bash
docker exec omnichannel-cx-project-api-1 python -c "import os,httpx,datetime; t=os.environ['WHATSAPP_ACCESS_TOKEN']; d=httpx.get('https://graph.facebook.com/debug_token',params={'input_token':t,'access_token':t},timeout=20).json().get('data',{}); e=d.get('expires_at'); print('valid:',d.get('is_valid'),'| expires:', 'NEVER' if e==0 else datetime.datetime.fromtimestamp(e,datetime.UTC).isoformat() if e else '?','| scopes:',d.get('scopes'))"
```
- `valid: True` + `expires: NEVER` → System User token, good.
- `expires:` a near timestamp → still temporary; it WILL die mid-demo. Replace before proceeding.
- `valid: False` → container didn't load the new token → the ④ shell trap; recreate api from a clean shell.

### e. ngrok tunnel up on the RIGHT domain
```bash
docker compose logs ngrok --tail 20    # confirm it started the tunnel on the .env NGROK_DOMAIN
```
Then confirm Meta's webhook callback URL points at `https://<that-domain>/integrations/whatsapp/webhook`.

### f. Neo4j reseeded (5 customers)
```powershell
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/neo4j/status"
# node_counts.Customer should be 5
```

### g. KB indexed / RAG healthy
```powershell
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/rag/health"
```

### + email / CRM (verify if the demo shows them)
```powershell
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/email/status"        # gmail_ready: true (SMTP outbound)
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/email-inbox/status"  # IMAP inbound
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/crm/status"          # configured: true (Jira)
```

### h. Empty inbox (clean slate confirmed)
```powershell
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/conversations"   # expect empty list
```

### i. END-TO-END real WhatsApp (the only check that proves the whole chain)
Send one real inbound from a Meta-verified number; confirm the reply **lands on the phone**. This is
the single test that exercises ngrok → webhook → Groq/Ollama → Neo4j → KB → Meta outbound together.
Watch `docker logs omnichannel-cx-project-api-1` for `outbound_delivery_failed`.

---

## Quick reference — happy path (once token + shell are clean)
```bash
docker compose down
docker volume rm omnichannel-cx-project_cx-data omnichannel-cx-project_neo4j-data omnichannel-cx-project_opensearch-data
docker compose up -d
docker compose up -d --force-recreate ngrok
# then: POST /admin/rag/index?recreate=true, and run the ⑧ verification checklist
```

## Notes / gotchas learned the hard way (see session log Sessions 7–8)
- A **fresh start makes ZERO Groq/LLM calls** — reseed uses `openpyxl` + a local SentenceTransformer,
  not Groq. It does not burn the 500K/day Groq quota. What burns quota is running many **test
  conversations** afterward (opportunity_generation is the heaviest per-message cost).
- Groq quota is a **rolling 24h window**, not a midnight reset.
- Neo4j `/load` is also exposed as `POST /admin/neo4j/load` (MERGE-based, safe to re-run) if the
  startup auto-seed ever doesn't fire.
- `WHATSAPP_LOCAL_TEST_MODE=true` does **not** simulate the production outbound path — the real Meta
  adapter always calls Graph API, so a bad token surfaces as a live 401 even with that flag set.
