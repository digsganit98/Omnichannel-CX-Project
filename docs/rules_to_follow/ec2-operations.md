# EC2 — the hosted instance: what it is, how to change it, what never to do

**This is the single source of truth for the hosted box.** Everything needed to operate EC2
lives here: why it exists, how it differs from local, its current state, the deploy and
fresh-start procedures, and the traps that have already bitten.

**Updating this document requires the user's explicit permission** — the same rule that governs
every other file in the repo. Update it when a permanent change is made to the EC2 box, or when
the user asks for something to be written here, and in both cases propose the change and wait for
approval first. Do not treat it as housekeeping to be kept current unprompted.

**What is NOT here:** the dated narrative of past deploys. Those stay in
`Sayantini-session-changes-log.md` alongside the fixes they shipped; § 9 below indexes them.

---

## 1. Why EC2 exists

It is **the hosted demo clients see** — a public IP serving the app, so the product can be shown
without a laptop being present.

More importantly, **EC2 is the sole holder of the shared external resources**: the Meta WhatsApp
number, the support mailbox, and the reserved ngrok domain. Each can only be held by one machine
at a time. A laptop that takes one steals it from the live demo, silently and with no error.

That is why local ships with `IMAP_ENABLED=false`, no `NGROK_DOMAIN`, and ngrok behind
`profiles: ["tunnel"]` so a plain `docker compose up` never starts it.

---

## 2. Local vs the hosted instance

Originally scattered through Fix 146/146a/148 as narrative, collected so a new session does not
have to reconstruct it from three entries.

### They are not the same machine and are not meant to be

| | local | EC2 (`ip-172-31-38-51`) |
|---|---|---|
| what it is for | writing and testing code | the hosted demo clients see |
| public address | none | public IP, port 8889 open to the internet |
| API port | 8888 | **8889** |
| shared resources | **takes none** | **holds all of them** |
| git | a real checkout | **no git at all** - `fatal: not a git repository` |

**EC2 is the sole holder of the shared external resources**: the Meta WhatsApp number, the
support mailbox, and the reserved ngrok domain. A laptop that takes one of those steals it
from the live demo, silently. That is why local ships with `IMAP_ENABLED=false`, no
`NGROK_DOMAIN`, and ngrok behind `profiles: ["tunnel"]` so `docker compose up` does not
start it.

### What must MATCH

Application code - `services/`, `apps/`, `shared/`, seed data, the KB. EC2 running old
code is what caused Fix 146: the deploy was a hand copy that omitted `data/` entirely, the
Neo4j seed threw `FileNotFoundError`, `_seed_neo4j()` swallowed it, and the app served
every customer as Unverified for months while looking healthy.

### What SHOULD differ, deliberately

`docker-compose.yml`. It already diverges twice and both are correct:

- **Ollama is commented out on EC2** (service, `ollama-pull`, and the api's
  `depends_on: ollama` - leave that and compose fails on an undefined dependency). The
  image was 5.5 GB on a 94%-full disk and its volume was **1.59 kB**, so no model had ever
  been pulled and the fallback did not exist there anyway.
- **ngrok has NO `profiles: ["tunnel"]` on EC2.** The profile exists to stop laptops taking
  the tunnel; EC2 is the machine that should hold it. Copying the local compose there means
  the next `docker compose up` starts no ngrok and **WhatsApp inbound goes silent with
  nothing to say why**.

### The three deploy traps, all of which have already bitten

1. **There is no git.** `git pull` cannot work. Files go up by `scp`, one at a time.
2. **`docker compose restart` runs OLD code.** Only `apps/admin-ui` is bind-mounted; every
   Python change needs `docker compose build api`. `docker cp` works and is the wrong fix -
   it leaves the image stale and the container diverged from the repo, which is the exact
   condition behind Fix 146.

   **A code-only rebuild is CHEAP - measured 2026-09-10, not assumed.** `COPY . .` is the LAST
   layer in `infra/docker/Dockerfile.api`; both `pip install` layers (torch + deps, the ~2 GB
   bulk) are cached and do NOT re-run when only application code changes. At **97% disk** the
   rebuild took **2.5 seconds** and cost ~200 MB. Two earlier deploys deferred Python fixes on
   the belief that a rebuild was too expensive at 95% disk - **that belief was wrong**, and it
   left the box serving a stale image for days. Rebuild when Python changes; the cost is the
   old image going dangling, not a 2 GB re-download.
3. **`docker compose restart` also does not re-read `.env`.** It reuses the existing
   container and its original environment. Only `docker compose up -d api` recreates it.
   `RAG_BACKEND=neo4j` was set, the container was restarted, and the app still reported
   `opensearch` with a clean startup log and no error anywhere.

### Do NOT do these on EC2 (see also § 7)

- **Do not touch other teams' containers, images or volumes.** ~42 containers across ~30
  projects share the box. The 22.5 GB `pwm-chatbot-dependencies_langfuse_clickhouse_data`
  volume is the largest thing on the disk and is not ours.
- **Do not raise OpenSearch's disk watermark.** It was considered and rejected: setting
  flood stage to 99% would let OpenSearch write until ~1.5 GB remained on a disk shared by
  every other team, to save a tens-of-MB index. The KB now lives in Neo4j, which has no
  such gate - that is what unblocked it at 94% without freeing a byte.
- **Do not remove OpenSearch from EC2.** Nothing uses it now (`RAG_BACKEND` defaults to
  neo4j), but it is the rollback, and re-pulling 1.34 GB onto a 94% disk may fail.
- **Do not `docker system prune --volumes`.** It would destroy `cx-data` - the SQLite DB
  and the seeded `data/` payload - and other teams' volumes with it.

### Facts worth not rediscovering

- **ngrok needs no port and none was assigned.** It dials OUT and holds the connection
  open, so nothing connects inbound to the instance. The person who provisioned the box
  gave three ports - 8889, 8025, 7474 - and was right that ngrok is not a fourth. Port 4041
  is ngrok's own dashboard, bound on the host only.
- **EC2 does not actually need ngrok.** It has a public IP and 8889 already answers from
  the internet. Meta requires HTTPS for webhooks and 8889 is plain HTTP, so this needs a
  certificate - a real task, not a cleanup, and it would end the shared-domain contention
  permanently.
- **The same `.pem` that unlocks the box sits ON the box**, in two other projects'
  directories (`dataforge_v2/`, `Document Comparison/`). Not ours to fix, not in our repo,
  never committed - `*.pem` is gitignored and `git check-ignore` confirms it.
- **Disk has been 93-96% all session** and drifts upward on its own as other teams build.

---

## 3. CURRENT STATE  (overwrite this block on every deploy; do not append)

**The box has no git and no record of its own commit, so this block is the ONLY place its state
exists.** The procedure for changing it is § 5-6 below. Do NOT follow the local wipe procedure
in `CLAUDE.md` on EC2 - it wipes `cx-data`, which here destroys the seed payload.

**As of 2026-09-22, after the Fix 167-191 deploy + rebuild + fresh start below.**

| | |
|---|---|
| code level | **`0b4f169`** - branch `Sayantini-phase2-ui-changes`, which contains BOTH this branch's Fixes 167-191 and `origin/main`'s audit-run browser (merged 2026-09-22). NOT equal to `main`, which is still missing the 25 commits. **Image rebuilt** so Python matches. Record the hash, never a status word |
| host | `ip-172-31-38-51`, public **13.233.212.194**, repo `/home/ec2-user/Omnichannel-CX-Project` |
| API port | **8889** (local is 8888) |
| git | **binary IS installed** (`/usr/bin/git` 2.50.1) and `git ls-remote` on the GitHub repo answers WITHOUT auth - measured 2026-09-22. The repo directory is still not a checkout, so `scp` remains the route in. **2 of ~30 projects on this box use git; `scp` is the house convention here** - do not convert this one without deciding that deliberately |
| `GROQ_MODEL` | **`openai/gpt-oss-120b`** - DIVERGED from local's `20b`, deliberately |
| Groq quota | **shared with local** - same `GROQ_API_KEY`; a probe from either machine answers for both. Seen live 2026-09-22: three SDK retries (3s/15s/16s) then give-up on a case_review, which rendered "Summary unavailable right now." while the rule-based cards beside it stayed populated. Cleared on Refresh |
| `RAG_BACKEND` | **`neo4j` by CODE DEFAULT - the variable is UNSET.** Confirmed still unset 2026-09-22 (present in local `.env`, absent here). `config.py` supplies it - do not "fix" the empty output |
| data | **0 conversations / 0 tickets** (fresh start 2026-09-22); **5** seeded customers; KB **14/14**, errors 0; `holdings_linked` **123**; Concepts **18**; **12 Service Desk agents** |
| logins | **DESTROYED by the 2026-09-22 wipe** - portal + admin need re-signup (`sayantini.s.55@gmail.com` / `7890864700`, must match the seeded record) |
| containers | all 5 up; **ngrok holds the shared tunnel** - untouched through the whole 2026-09-22 deploy, verified by unchanged uptime at every step; opensearch UNUSED (kept as rollback, untouched); Ollama commented out of compose |
| disk | **~29 GB free, 82%** - measured 2026-09-22, the healthiest recorded. Earlier entries said 93-96% |
| backups on box | **`~/backup_post191/code_post191.tar.gz`** (1.1M, 2026-09-22: `apps services shared scripts tests .gitignore docker-compose.yml .env`). Everything else in `~` was deleted 2026-09-22 - see below |

**`/app/data` NOW SHIPS IN THE IMAGE - the Fix 146 defect is CLOSED.** Measured 2026-09-22:
`docker run --rm --entrypoint sh <api image> -c "ls -l /app/data/..."` lists `bfsi.xlsx`
26,418, `knowledge_base/InboxIQ_BFSI_KB.pdf` 48,094, `resolution_kb/resolution_examples.json`
12,109. The cause was never gitignore - all three are tracked - it was that the original hand
`scp` deploy omitted `data/` entirely. `scp -r data` on 2026-09-22 fixed it permanently.

**Proven by the wipe itself, not by reasoning:** `cx-data` was destroyed and the api restarted
with NO copy-in step. The log read `bfsi_data_loaded` then `neo4j_seed_complete`, and the graph
came back with Customer 5. On every previous wipe this threw `FileNotFoundError`, which
`_seed_neo4j()` swallowed - the bug that served customers as Unverified for months.

**Consequently the loose seed files in `~` were deleted 2026-09-22** (`bfsi.xlsx`,
`InboxIQ_BFSI_KB.pdf`, `resolution_examples.json`, `seed_backup_bfsi.xlsx`, `seed_backup_rkb/`,
`probe_ec2.py` - a one-off KB retrieval diagnostic). They existed ONLY as the hand-install
sources and rescue copies for a volume-only payload. `seed_backup_kb` and all four
`backup_pre*` folders were **already gone before that delete** - by whom is not known.

**The Service Desk bench now reseeds itself.** Fix 191 added an `on_event("startup")` hook
beside `_seed_neo4j()`; `scripts/seed_service_desk_agents.py` used to be called from nowhere,
so every wipe left the board with no one to auto-assign to. Verified here: 12 agents present on
the first boot after the wipe, with no manual script run.

### Known defects LIVE on this box

- **Three escalation gates are constants** (measured 11/11 locally). `_is_strong_l1_knowledge_answer`
  skips the handoff check, so a question the KB cannot answer can auto-send with invented
  generality in it. Shipped with the Fix 152 deploy; unfixed.
- **A 429 sends the raw record dump to the customer** - `generation.get("text") or raw_data`,
  unguarded. The per-minute token ceiling (8,000) is what trips, and it tripped locally on
  2026-09-06.
- **Six Concepts have zero KB chunks**, Fixed Deposit among them, held by 4 customers.
- **Three KB chunks link to nothing** - `demat_account`, `sip_investment`, `elss_tax_benefit`.
  Expected: no seeded customer holds those.

---

## 4. How to work on the box

### Standing facts

- **Box:** `ip-172-31-38-51`, public **13.233.212.194**, repo at
  `/home/ec2-user/Omnichannel-CX-Project`, API on port **8889** (local is 8888).
- **No git on the box.** Verified: `fatal: not a git repository`. `scp` is the only route in,
  and nothing there records its commit - **section 3 above is the sole record of its state**.
- **Shared machine.** ~30 projects, ~42 containers. Disk has sat at 93-96% for weeks.

### Who runs what

**Claude prepares the commands; the user runs them and reports the output.** Claude has no SSH
access, no credentials, and does not ask for them. A deploy is handed over as a paste-ready
block - never "let me SSH in and look". If a fact about the box is needed, give the one command
that answers it and wait.

**Paste-ready means no placeholders.** `ec2-user@<host>` was handed over twice; in a shell `<` is
a redirect, so it mangled the command. Fill every value, or say plainly which single line the
user must edit.

### Which prompt runs which

| prompt | runs |
|---|---|
| `PS C:\...>` | `scp` **only** |
| `[ec2-user@ip-172-31-38-51 ...]$` | everything else |

They look alike. Running `scp` on EC2 makes the box SSH to itself and fail - this has already
cost a cycle. **PowerShell takes ONE LINE per command**; a backslash continuation is Git Bash
syntax and breaks there.

### The four rules the user enforces

1. **Check state before changing anything.**
2. **Explain what and why, then WAIT.** Proposing a state-changing command and running it in the
   same breath has been corrected every time.
3. **Never touch another team's anything.**
4. **Say plainly when something is not within your authority.** At 96% disk with nothing of ours
   reclaimable, the answer is "someone else has to do this" - not a workaround that degrades a
   shared safety limit.

### `.env` - shared origin, since diverged

**EC2's `.env` was copied from local, then BOTH were edited independently.** They share the same
`GROQ_API_KEY` - **one Groq quota across both machines** - while other values differ per box. It
is gitignored, so it appears in NO git diff: a question about `.env` can never be answered from
`git log`, only by reading the value on each machine.

**Never print `.env` to read one value.** A `grep -vE "KEY|TOKEN|PASSWORD|SECRET"` filter matches
only variable NAMES, so secrets named anything else (e.g. `NEO4J_AUTH`) print in full - done on
2026-09-07 on the hosted box, and it bought nothing the code diff could not answer. Grep the one
variable by name: `grep "^GROQ_MODEL=" .env`.

**Whether a deploy needs an `.env` change is answerable from the code:**
`git diff <base>..HEAD -- services/ apps/` and grep the added lines for `getenv`/`environ`.

**Two Groq limits, and confusing them leads to switching models for no reason.** The 429 that
moved local off 120b was the TOKENS-PER-MINUTE ceiling (8,000), not the daily request cap. Read
both from the headers of one `max_tokens:1` probe: `x-ratelimit-remaining-requests` (daily) and
`x-ratelimit-remaining-tokens` (per minute).

---

## 5. Deploying - the 11 steps

1. **Read state first.** `df -h /`, `docker compose ps`, plus whatever the change touches. It is
   a live box other teams depend on - never change before reading.
2. **Find the key before using it.** `ls ganit-genai-solutions.pem`. It has moved between the
   parent and project directories; a stale path fails with `Permission denied (publickey)`, which
   reads as auth and is actually a missing file.
3. **Copy each file to its FINAL path - one `scp` per file.** No staging directory, no second
   `cp` pass.

       scp -i ganit-genai-solutions.pem services/rag_service/config.py ec2-user@13.233.212.194:~/Omnichannel-CX-Project/services/rag_service/config.py

4. **Back up anything being overwritten**, on EC2, before copying:
   `mkdir -p ~/backup_<label> && cp <files> ~/backup_<label>/`
5. **Verify the files landed - BEFORE rebuilding.** `grep -c "<string only the new version has>"
   <file>`. Disk presence is not enough; grep for content, and compare the count against the same
   grep run locally. A predicted number is not a check - `grep -c` counts LINES, not occurrences.
6. **`docker compose build api`** - not `restart`. Only `./apps/admin-ui` is bind-mounted, so
   every Python change needs a rebuild.
7. **`docker compose up -d api`** - not `restart`. Restart reuses the container and its original
   environment, so `.env` changes do not take.
8. **Verify from INSIDE the container** - that the app sees the change, not just that the file is
   on disk: `docker compose exec api python -c "..."`.
9. **Run whatever admin endpoint the change needs** (`/admin/rag/index`, `/admin/rag/link-kb-graph`)
   and read the result.
10. **Confirm nothing else moved** - disk unchanged, other teams' containers untouched.
11. **Log it**: update section 3 above with the fix level the box is left at, and add the dated
    narrative to the session changes log. Record commit hashes - never status words like
    "UNCOMMITTED", which rot into lies the next session then believes.

**UI-only changes skip 6-8.** `apps/admin-ui` is bind-mounted, so the files take effect the moment
they land. **Docs-only changes** (`README.md`, `.env.example`) skip 5-9 entirely.

---

## 6. Fresh start - full wipe and reseed, the 8 steps

**The local wipe procedure (`CLAUDE.md`, "Wiping data") is DANGEROUS on EC2.** It says wipe
`cx-data`, which is safe locally - the seed files ship inside the image - but on this box
`cx-data` is the ONLY copy. Do not follow it here. Use this.

**NO LONGER TRUE as of 2026-09-22 — `/app/data` now ships in the image.** This paragraph used
to read "Step 1 is the whole procedure: `/app/data` exists ONLY in the `cx-data` volume",
measured 2026-09-07 when `docker run --rm --entrypoint sh <api image> -c "ls /app/data"` gave
**no such directory**. `scp -r data` on 2026-09-22 put the three files on disk, the rebuild
carried them in via `COPY . .`, and the same probe now lists all three at 26,418 / 48,094 /
12,109 bytes. A wipe no longer destroys them.

**Re-run that probe before any wipe anyway.** It is one read-only command, and it is the single
check that says whether steps 1, 6 and 7 are needed. Empty output means the payload is
volume-only again and the struck-through steps come back.

> **Correction, 2026-09-16 — why, and why it matters.** This paragraph used to say "`data/` is
> gitignored so `COPY . .` never carried it." **That is false for this repo.** `.gitignore`
> excludes only `data/*.db`, `data/exports/*` and `data/uploaded_docs/*`; `.dockerignore`
> excludes only `data/*.db`. All three seed files are tracked (`git ls-files --error-unmatch`
> confirms) and the local fresh start on 2026-09-16 proved the image carries them —
> `docker compose exec api ls /app/data` listed `bfsi.xlsx`, `knowledge_base/` and
> `resolution_kb/`, and `_seed_neo4j()` logged `neo4j_seed_complete` with no
> `FileNotFoundError`.
>
> The real cause is **there is no git on EC2**: the payload is missing because the hand-`scp`
> deploy omitted it (the Fix 146 defect), not because anything ignores it. This matters
> because it changes the fix. **Steps 1, 6 and 7 below exist only to work around the missing
> payload** — back it up, copy it back, restart to re-run a seed that was guaranteed to fail
> the first time. Rebuilding the EC2 image from a complete copy of the repo would carry
> `data/` in via `COPY . .` and remove the need for all three. That rebuild is cheap:
> **measured 2.5s at 97% disk** (§ 2, trap 2).
>
> **DONE 2026-09-22. That rebuild has now happened** — `scp -r data` put the payload on disk,
> the image picked it up via `COPY . .`, and a real wipe then reseeded from it with no copy-in
> step (`bfsi_data_loaded` → `neo4j_seed_complete`, Customer 5). **Steps 1, 6 and 7 below are
> therefore OBSOLETE — skip them.** They are kept, struck through, because they describe the
> shape of a defect that lasted months and a future hand-deploy could reintroduce it by
> omitting `data/` again. If `docker run --rm --entrypoint sh <api image> -c "ls /app/data"`
> ever comes back empty, the payload is volume-only again and these three steps come back.

1. ~~**Copy the payload off, and verify the sizes before continuing.**~~ **OBSOLETE — skip.**
   `docker cp omnichannel-cx-project-api-1:/app/data/bfsi.xlsx ~/seed_backup_bfsi.xlsx`
   (same for `knowledge_base` to `~/seed_backup_kb`, `resolution_kb` to `~/seed_backup_rkb`).
   Expect ~26,418 / ~48,094 / ~12,109 bytes. **If any is empty, STOP.**
2. `docker compose stop api neo4j` - **NOT `down`**: that stops ngrok (holding the shared tunnel)
   and OpenSearch (unused, but re-pulling 1.34 GB at 95% disk may fail).
3. `docker compose rm -f api neo4j` - **a STOPPED container still holds its volumes**;
   `volume rm` fails with "volume is in use" until this runs. `docker inspect` the holder ids
   first and confirm they are ours - never remove another team's container.
4. `docker volume rm omnichannel-cx-project_cx-data omnichannel-cx-project_neo4j-data` - only
   these two.
5. `docker compose up -d neo4j`, then WAIT for `(healthy)` - a fresh empty store took ~90s.
   Seeding against a not-ready database fails.
6. `docker compose up -d api` - this recreates the empty `cx-data`. **The seed now SUCCEEDS on
   this first boot**: expect `bfsi_data_loaded` then `neo4j_seed_complete`, because the payload
   comes from the image. Fix 191's hook also seeds the **12 Service Desk agents** here.
   ~~then `docker cp` all three payloads back in ... the first boot's seed WILL fail with
   FileNotFoundError~~ **OBSOLETE — skip.**
7. ~~`docker compose restart api` - so `_seed_neo4j()` re-runs now the file is there.~~
   **OBSOLETE — skip.** There is nothing to copy in, so nothing to restart for.
8. Re-index: `POST /admin/rag/index?recreate=true` then `POST /admin/rag/link-kb-graph`, reading
   the admin key out of the container first with `docker compose exec -T api printenv
   ADMIN_API_KEY`. Expect `indexed 14/14 errors 0` and `holdings_linked: 123`.

**Then:** logins were destroyed with `cx-data`. Sign up again on the portal as
`sayantini.s.55@gmail.com` / `7890864700` - must match the seeded record or identity resolution
treats it as an unknown customer. Admin console signup too (deliberately open, Fix 145).

**Two log lines that look like failures and are not:** `label Customer does not exist` is the seed
checking an empty graph; a 404 on an old `conv_*` id is someone's open browser.

**Verify:** `Customer 5`, `KBChunk 14`, `Concept 18`, `INSTANCE_OF 143`; conversations/turns/
tickets all 0; ngrok + opensearch + mailpit still "Up N days"; disk unchanged.

### Before a real-WhatsApp demo — check the Meta token FIRST

*(Moved here 2026-09-16 from `fresh-start-runbook.md`, which was deleted: it was written as a
local procedure but this content is EC2's, because EC2 holds the WhatsApp number.)*

**An expired token has broken the demo 3× already.** Outbound calls Meta's Graph API and
**401s the moment the token expires**. Temporary tokens from the Graph API Explorer last
hours. The permanent fix is a **System User token** (Meta Business Settings → System Users),
which does not expire. Put it in `.env` as `WHATSAPP_ACCESS_TOKEN` and **recreate the
container** — `docker compose up -d api`, not `restart`, which does not re-read `.env` (§ 2,
trap 3).

Then confirm what the container actually loaded:

```bash
docker compose exec -T api python -c "import os,httpx,datetime; t=os.environ['WHATSAPP_ACCESS_TOKEN']; d=httpx.get('https://graph.facebook.com/debug_token',params={'input_token':t,'access_token':t},timeout=20).json().get('data',{}); e=d.get('expires_at'); print('valid:',d.get('is_valid'),'| expires:', 'NEVER' if e==0 else datetime.datetime.fromtimestamp(e,datetime.UTC).isoformat() if e else '?','| scopes:',d.get('scopes'))"
```

- `valid: True` + `expires: NEVER` → System User token, good.
- `expires:` a near timestamp → still temporary; **it will die mid-demo.** Replace it now.
- `valid: False` → the container never loaded the new token; recreate it.

**`WHATSAPP_LOCAL_TEST_MODE=true` does NOT make outbound safe.** It guards *inbound* only —
the real Meta adapter always calls Graph API, so a bad token still surfaces as a live 401 and
a real send still reaches a real phone with that flag set.

Also confirm ngrok is up on the right domain (`docker compose logs ngrok --tail 20`) and that
Meta's webhook callback points at `https://<domain>/integrations/whatsapp/webhook`.

**The one check that proves the whole chain** is a single real inbound from a Meta-verified
number, confirming the reply lands on the phone: ngrok → webhook → Groq → Neo4j → KB → Meta
outbound. Watch for `outbound_delivery_failed` in the api logs.

---

## 7. Never

- **Never copy `docker-compose.yml`.** Verified divergent and correct - see section 2.
- **Never copy `.env`** - hand-maintained per box.
- **Never touch another team's containers, images or volumes.**
- **Never raise OpenSearch's disk watermark** to get an index built.
- **Never `docker system prune --volumes`** - destroys `cx-data` (SQLite + seeded `data/`) and
  other teams' volumes.
- **Never run `docker image prune` - not even without `-a`.** It is **daemon-wide, not
  project-scoped**, and "dangling images are safe to clear" is a statement about Docker, not about
  a shared box. Run on 2026-09-10 it deleted **~14 untagged `genai-demos/cam-automation` images,
  5.94 GB**, belonging to another team. Their tagged `frontend-latest` / `backend-latest` survived
  and nothing of theirs was running, so nothing broke - but those layers were not ours to reclaim
  and the owner had to be told. **Disk pressure is § 4 rule 4: someone else has to do this.** If a
  build genuinely needs headroom, ask the box's other owners; do not reclaim it unilaterally.
- **Never remove OpenSearch** - nothing uses it now, but it is the rollback and re-pulling
  1.34 GB at 95% may fail.

---

## 8. Traps and facts worth not rediscovering

- **`docker compose restart` runs OLD Python code.** Only `apps/admin-ui` is bind-mounted; all
  Python is baked into the image. A correct fix will appear to have failed. `docker cp` works and
  is the wrong fix - it leaves the image stale and the container diverged from the repo, which is
  the exact condition behind Fix 146.
- **`docker compose restart` also does not re-read `.env`.** Only `docker compose up -d api`
  recreates the container. `RAG_BACKEND=neo4j` was set, the container restarted, and the app still
  reported `opensearch` with a clean log and no error anywhere.
- **`/app/data` is a named volume** (`cx-data`), so a rebuilt image cannot fix a missing file
  there - `docker cp` into the running container is what lands it.
- **ngrok needs no port** - it dials OUT. EC2 does not strictly need it (public IP, 8889 answers),
  but Meta requires HTTPS, so replacing it needs a certificate first.
- **`ERR_NGROK_334` "endpoint already online"** on a fresh start means a teammate is holding the
  shared free-tier domain from their own machine - not a local bug. Check `Get-Process ngrok`
  locally first; if nothing, it is external and retrying cannot win. Ask them to stop.
- **WhatsApp is on a Meta TEST number** (confirmed 2026-09-09 in the Meta console: "Claim a
  WhatsApp test number - Completed", under a "Test WhatsApp Business Account"). A test number
  accepts inbound from **anyone**, but may only SEND to the five-or-fewer recipients manually
  added in the dashboard. A customer not on that list has their message processed correctly and
  the reply silently rejected by Meta - observed 2026-09-09 with a real customer whose number was
  then added. Auth is not the problem: a System User token (`Omnichannel_WhatsApp_Backend`) is in
  place and does not expire in hours.
- **A Groq 429 is CACHED as "no offers".** `opportunity_generation` runs LAST of the ~6 LLM calls
  a message fires, so it is the one refused when the per-minute ceiling is hit. The failed run
  still writes an `opportunity_evaluations` row, and `apps/api/routes/agent_assist.py:175` returns
  that cached result on every later Refresh **without retrying the LLM** - so a single rate-limited
  call suppresses offers for that conversation until the input hash changes. The card reads "No
  offers right now", identical to a genuine empty result. **Refresh cannot clear it; a new turn
  can.** Observed 2026-09-10. Same family as the failed-send trap below: a failure rendering as a
  normal result.
- **One message on 120b costs ~12,000 tokens against an 8,000/minute ceiling.** Measured
  2026-09-10 from `llm_usage_events`: intent 2,867 + answer 4,030 + resolution 1,299 + handoff 601
  + case_summary 663 + customer_context 2,902. **Messages sent back-to-back WILL 429 on the last
  call** - pace a demo at roughly one message per minute. This is the TPM limit, not the 1,000/day
  request cap; § 4 warns about confusing the two.
- **A failed outbound send still renders as "sent" in the admin UI.** All three failure paths in
  `services/channel_service/delivery.py` return a dict the UI treats as success, so a Meta
  rejection, a local-log fallback and a real delivery are indistinguishable on screen. The only
  way to know is the container log or the recipient's phone.
- **The same `.pem` that unlocks the box sits ON the box** in two other projects' directories.

---

## 9. History - what has been done to the box

Dated narrative lives in `Sayantini-session-changes-log.md`; this is the index.

| when | what | where the detail is |
|---|---|---|
| 2026-09-07 | Fix 148 to 152; the KB index existed on EC2 for the first time | log section "EC2 deploy - 2026-09-07" |
| 2026-09-07 | Full wipe and reseed; the seed payload that exists in only one place | log section "EC2 fresh start - 2026-09-07" |
| 2026-09-07 | Fix 152 to 162, UI only, no rebuild | log section "EC2 deploy 2026-09-07 (second)" |
| 2026-09-07 | Fix 163 - the browser tab title | log section "EC2 deploy - Fix 163" |
| 2026-09-10 | Fix 164-166 + Digvijay's merge; first **rebuild** and fresh start since 09-07; box reached parity with `main` at `f7b6f71` | log section "EC2 deploy - 2026-09-10" |

**Everything committed to `main` is deployed.** The box is at `f7b6f71`, image included. Verify
with the greps in § 3 rather than trusting this line - it decays the moment anyone commits.
