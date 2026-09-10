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
exists.** The procedure for changing it is § 5-6 below. Do NOT follow `fresh-start-runbook.md`
on EC2 - it is written for local and its `cx-data` wipe destroys the seed payload.

**As of 2026-09-07, after the Fix 153-162 UI deploy below.**

| | |
|---|---|
| code level | **Fix 163 (UI only)** - matches local for `apps/admin-ui/`; the two changed Python files from the Fix 162 deploy are ON the box but NOT yet in the image (see below) |
| host | `ip-172-31-38-51`, public **13.233.212.194**, repo `/home/ec2-user/Omnichannel-CX-Project` |
| API port | **8889** (local is 8888) |
| git | **none** - `scp` is the only route in |
| `GROQ_MODEL` | **`openai/gpt-oss-120b`** - DIVERGED from local's `20b`, deliberately: probed 2026-09-07 at 999/1000 requests, healthy |
| Groq quota | **shared with local** - same `GROQ_API_KEY`; a probe from either machine answers for both |
| `RAG_BACKEND` | `neo4j` - verified inside the container |
| data | 0 conversations / 0 turns / 0 tickets; **5** seeded customers; KB **14/14**; `holdings_linked` 123 |
| logins | **DESTROYED by the wipe** - portal + admin need re-signup (`sayantini.s.55@gmail.com` / `7890864700`) |
| containers | all 5 up, **untouched by this deploy** (api + neo4j 17h, ngrok/opensearch/mailpit 2d); **ngrok holds the shared tunnel**; opensearch UNUSED (kept as rollback); Ollama commented out of compose |
| disk | **8.5 GB free, 95%** (measured this deploy) - shared with ~30 other projects |
| backups on box | `~/seed_backup_bfsi.xlsx`, `~/seed_backup_kb`, `~/seed_backup_rkb` (the irreplaceable payload), `~/backup_pre149` (8 files), `~/backup_pre162` (the 5 files that deploy overwrote), **`~/backup_pre_title`** (`index.html`, Fix 163) |

**`/app/data` exists ONLY in the `cx-data` volume** - the api image has no such directory
(measured). `bfsi.xlsx`, the KB PDF and the resolution examples were hand-copied in and exist
nowhere else. **Any wipe must copy them off first.**

**The UI is live; two Python strings are not.** `apps/admin-ui/` is bind-mounted, so the four
UI files took effect the moment they landed - no rebuild, no restart, nothing else on the box
disturbed. `apps/api/main.py` and `apps/api/routes/email.py` are also on the box but the image
still holds the old copies, so `/` and the OpenAPI title still read **"Omnichannel CX
Accelerator"** and the SMTP test body still names it. **Deliberately not rebuilt**: three strings
nobody sees are not worth spending image-build headroom at 95% disk. They will correct themselves
on the next rebuild anyone does for a real reason - no further action is needed to "finish" this
deploy.

**Verified after copying** (content, not disk presence): every grep count on the box matched
local exactly - `homePage` 1, `rel="icon"` 1, `OmnichannelCX` 3, `an-tabs` 1, `1701d0` 1,
`openLogin` 2, logo **2,889 bytes**. Then from inside the box: `/admin-ui` serves the home page,
`/admin-ui/assets/ganit-logo.png` returns 200, and `/` still returns the old name - which is the
expected split. The user opened `http://13.233.212.194:8889/admin-ui` and confirmed it renders.

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

**`docs/rules_to_follow/fresh-start-runbook.md` is written for LOCAL and is DANGEROUS on EC2 as
written.** It says wipe `cx-data`. Do not follow it there. Use this.

**Step 1 is the whole procedure: `/app/data` exists ONLY in the `cx-data` volume.** Measured
2026-09-07: `docker run --rm --entrypoint sh <api image> -c "ls /app/data"` gives **no such
directory**. `data/` is gitignored so `COPY . .` never carried it. `bfsi.xlsx`, the KB PDF and
`resolution_examples.json` were hand-copied in during Fix 146 and exist NOWHERE else. Wipe the
volume without copying them off and they are gone for good.

1. **Copy the payload off, and verify the sizes before continuing.**
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
6. `docker compose up -d api` (this recreates the empty `cx-data`), then `docker cp` all three
   payloads back in. There is nothing to copy into until the volume exists. **The first boot's
   seed WILL fail with FileNotFoundError - expected, it is swallowed, ignore it.**
7. `docker compose restart api` - `_seed_neo4j()` runs at startup only, and now the file is
   there. Expect `neo4j_seed_complete`. (`restart` is right here: no code or `.env` change.)
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

---

## 7. Never

- **Never copy `docker-compose.yml`.** Verified divergent and correct - see section 2.
- **Never copy `.env`** - hand-maintained per box.
- **Never touch another team's containers, images or volumes.**
- **Never raise OpenSearch's disk watermark** to get an index built.
- **Never `docker system prune --volumes`** - destroys `cx-data` (SQLite + seeded `data/`) and
  other teams' volumes.
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

**Not yet deployed:** Fix 164 and Fix 165 (the home page - bands, viewport tiers, Ganit colours)
are committed locally but the box is still at Fix 163.
