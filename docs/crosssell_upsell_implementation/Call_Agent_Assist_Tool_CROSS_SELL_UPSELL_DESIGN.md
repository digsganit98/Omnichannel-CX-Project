# Real-Time Cross-Sell / Up-Sell Recommendation Engine ("Nudges")
### Design & Implementation Reference — extracted from Call_Agent_Assist_Tool

This document describes the architecture, data contracts, prompts, orchestration logic, and lessons learned from the Call Agent Assist Tool's nudge engine, so the same pattern can be reimplemented in another project. It is domain-agnostic where possible; insurance-renewal specifics are marked as **[domain]** so you can swap them out.

---

## 1. What the system does

During a live agent–customer call, the system maintains a rolling set of **exactly 3 "nudges"** on the agent's screen — short, speakable suggestions (10–12 words) that:

- resolve the customer's current concern,
- move the conversation toward the business goal (**[domain]**: policy renewal), and
- surface cross-sell/up-sell opportunities **only at the right call stage**.

Alongside nudges, the system produces per-turn **insights**: a customer-fact summary, an intent meter (0–100), a short "current intent" phrase, and the detected call stage.

---

## 2. High-level architecture

```
                        ┌──────────────────────────────────────────────┐
 Live audio ──► STT ──► │  Rolling transcript (last ~700 tokens)       │
 (Azure Speech)         └──────────────┬───────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────────┐
        │                              │                                  │
        ▼                              ▼                                  ▼
┌───────────────┐          ┌────────────────────┐            ┌─────────────────────┐
│ insight_func  │          │ listening_nudges   │            │ BERT pre-filter     │
│ (LLM, every   │          │ (LLM "listener",   │            │ (local MiniLM,      │
│  few turns)   │          │  cheap/fast model) │            │  cosine similarity)  │
│  → Summary    │          │  → SpokenFlag      │            │  → relevant library  │
│  → Intent 0-  │          │  → Status          │            │    sections/questions│
│    100        │          │  → update_flag     │            └──────────┬──────────┘
│  → IntentCapt.│          └─────────┬──────────┘                       │
│  → CallStage  │                    │ update_flag == "Yes"             │
└───────┬───────┘                    ▼                                  │
        │              ┌──────────────────────────────┐                 │
        │ intent,      │ update_active_nudges         │ ◄───────────────┘
        └────────────► │ (LLM "generator", stronger   │ ◄── RAG documents
                       │  model, temp 0.3)            │ ◄── customer context
                       │  → new 3-nudge list          │ ◄── previously-spoken nudges
                       └──────────────┬───────────────┘
                                      ▼
                          Agent UI (3 nudge cards + insights panel)
```

**Key design idea — split "listening" from "generating":**
- A **cheap, frequent listener** (`listening_nudges`) runs on every transcript update and only answers: *has the agent already said this? is this nudge still relevant? did the customer's intent change?*
- The **expensive generator** (`update_active_nudges`) runs **only when the listener raises `update_flag = "Yes"`**. This keeps latency and token cost down.

**Session lifecycle:**
1. **Call start (no transcript yet):** `update_active_nudges_proactive()` runs **once**, from the customer profile alone, producing the initial 3 nudges (loyalty acknowledgement + offer + urgency).
2. **During call:** loop of `insight_func` + `listening_nudges` → conditional `update_active_nudges`.
3. Everything is logged to per-session report files for QC.

---

## 3. Core data contract: the Nudge object

```json
{
  "Status": "Active" | "Inactive",
  "Nudge": "*Header Tag* - <10–12 word speakable sentence>",
  "SpokenFlag": "Yes" | "No"
}
```

- The list always holds **exactly 3** nudges, order-preserved.
- `Status = "Inactive"` → no longer relevant to the current topic → candidate for replacement.
- `SpokenFlag = "Yes"` → agent has *fully* delivered this content → candidate for replacement.
- Text format: `*Header Tag* - sentence`, e.g.
  `*Renewal Advantage Prompt* - Renewing now retains your 20% NCB and locks in your ₹1,200 premium savings for this year.`

### Insight object (from `insight_func`)

```json
{
  "SummaryInsights": "- bullet 1\n- bullet 2"   // or exactly "No" when nothing new,
  "Intent": 77,                                  // 0–100 purchase/renewal likelihood
  "IntentCapture": "Customer comparing competitor premium quote",  // <15 words
  "CallStage": "Price Objection Handling, Coverage Optimization"   // current, next
}
```

---

## 4. The four LLM functions

### 4.1 `insight_func(context, previous_result, intent_capture_history, call_stage_history)`
**Model:** standard chat model (e.g. GPT-4o class). **Runs:** every N transcript updates.

Prompt responsibilities (all in ONE call to save latency):
1. **SummaryInsights** — customer-focused facts only (never agent behaviour). Must be **additive**: the previous insights are passed in and the model is instructed to do *semantic* dedup ("extract the core concept of each previous insight; do not return paraphrases"). Give 2–3 concrete duplicate examples in the prompt — this materially improves dedup. Return literal `"No"` if nothing new. Keep each insight < 15 words.
2. **Intent (0–100)** — likelihood meter. Decrease on: refusal, competitor leaning, price objections, dissatisfaction. Increase on: agreement, add-on interest, positive sentiment. (Mapped to 10 buckets of 10 for UI display.)
3. **IntentCapture** — the customer's *current dominant intent* in <15 words; if unchanged vs. history, return the same text verbatim (gives you a cheap change-detector).
4. **CallStage** — classify against a **fixed enumerated list of stages** and return `current, next`. **[domain]** stage list used here:
   - Call Opening & Customer Verification
   - Current Policy Snapshot
   - Claim History Reference
   - Renewal Premium Explanation
   - Add-on Relevance & Usage Mapping
   - Competitor Quote Validation
   - Price Objection Handling
   - Coverage Optimization
   - Lapse Risk & Continuity Nudges
   - Claim Support Reassurance
   - Confirmation Before Closure
   - Payment & Documentation
   - Call Closure
   - Urgency

Output rules: JSON only, no markdown, no extra text. (Still sanitize — see §6.)

### 4.2 `update_active_nudges_proactive(nudge_library, nudges_list, call_context)`
**Runs:** once, at session start, before any transcript exists. **Model:** the stronger generator model.

Purpose: generate 2–3 **opening talking points** from the customer profile. Critical prompt lessons:
- Explicitly forbid "factual context" nudges (`*Vehicle Context* - Hybrid automatic, 15,000 km`) — the model loves producing these. Demand **talking points** with three ingredients: **acknowledgement** (loyalty/positive history), **offer** (specific benefit, discount, savings amount), **urgency** (deadline, expiring benefit).
- Include GOOD and BAD examples in the prompt (few-shot contrast works far better than rules alone).
- **No cross-sell/up-sell at this stage** — opening nudges build trust.
- Max 10–12 words per sentence (excluding header tag), because agents read them live.

### 4.3 `listening_nudges(live_transcript, nudges_list, intent_capture_history, present_intent_capture)`
**Model:** the cheaper/faster model. **Runs:** on every transcript update (frequently).

Logic (all semantic, explicitly "no keyword matching" in the prompt):
- **Current topic** is defined by the **latest customer turn only**; full transcript may be read only for SpokenFlag.
- `SpokenFlag = "Yes"` only when the agent has **fully** delivered a nudge's content — "mere mention, hint, or partial overlap does NOT count."
- `Status = "Inactive"` when the nudge's topic has been fully covered, or it's the least-relevant nudge after an intent change.
- `update_flag = "Yes"` when ANY of:
  a) any nudge is Inactive,
  b) ALL nudges have SpokenFlag = Yes,
  c) present intent differs semantically from intent history (intent shift),
  d) a nudge no longer matches the current intent (mark least relevant Inactive).
- `update_flag = "No"` only when all nudges Active, at least one unspoken, and no intent change.

Output format quirk that worked well: JSON object with `"nudges"` array, then **on a new line** the literal `update_flag=Yes|No`. Parsing splits lines, extracts the flag line, then JSON-parses the rest. (You could instead put the flag inside the JSON — simpler; this project kept it separate to make the flag extraction robust even when the JSON is malformed.)

### 4.4 `update_active_nudges(nudge_library, live_transcript, nudges_list, call_context, rag_documents, ongoing_intent, previously_suggested_nudges)`
**Model:** stronger model (GPT-4.1 class), `temperature=0.3`. **Runs:** only when `update_flag == "Yes"`.

Prompt structure — the important rules:

1. **Objective framing:** nudges are "renewal-focused micro-strategic steps," each one must move the customer one step closer to completion. **[domain]** — replace with your conversion goal.
2. **Call-stage gating of cross-sell/up-sell** (this is the key up-sell control):
   - **Early stage** (rapport, verification): trust-building only, **no upsell/cross-sell**.
   - **Mid-early** (pricing, objections, doubts): clarify and de-escalate, **no upsell/cross-sell**.
   - **Mid-late** (benefits reinforcement): **upsell allowed** — but only "if customer is happy."
   - **Closing** (decision, payment): commitment and process only, **no upsell/cross-sell**.
3. **Personalization inputs**, each in its own clearly-labelled prompt section:
   - Customer context (structured profile — see §5),
   - Ongoing intent ("all nudges should revolve around this intent"),
   - RAG documents (policy/product details for factual grounding),
   - Previously suggested nudges ("DO NOT return these or similar ones"),
   - Live transcript (last ~700 tokens).
4. **Nudge library as style guide, not copy source** — "use for tone, rhythm, patterns; NEVER copy directly."
5. **Lifecycle rules:** preserve `Active + SpokenFlag=No` nudges *exactly* (same text, same position); replace only `Inactive` or `Spoken` ones, in-place; always return exactly 3.
6. Ground price claims: "support points with the premium price when mentioned in context."

### Deterministic post-processing (CRITICAL — do not rely on the LLM to obey rule 5)

The LLM frequently rephrases nudges it was told to preserve. The code enforces preservation in Python:

```python
# Pseudo-code of the merge algorithm (used after every generator call)
original_texts = {n["Nudge"].strip() for n in nudges_list}
preserved = {}   # text -> updated nudge object (existing nudges the LLM returned)
new_nudges = []  # nudges whose text is not in original list
for n in llm_output:
    (preserved if n["Nudge"].strip() in original_texts else new_nudges).append_or_set(n)

result, i = [], 0
for orig in nudges_list:
    needs_replacement = orig["Status"] == "Inactive" or orig["SpokenFlag"] == "Yes"
    if needs_replacement:
        if i < len(new_nudges):
            result.append(new_nudges[i]); i += 1
        # else: drop the slot
    else:
        # keep the Active nudge even if the LLM omitted or rephrased it
        result.append(preserved.get(orig["Nudge"].strip(), orig.copy()))
while i < len(new_nudges) and len(result) < 3:
    result.append(new_nudges[i]); i += 1
```

Similarly, `listening_nudges` output is merged by **matching on nudge text** and copying only `SpokenFlag`/`Status` onto the originals — the LLM is never allowed to change nudge wording in the listener path.

On `JSONDecodeError`: keep the old list unchanged (fail-safe, the UI never blanks out).

---

## 5. Customer context extraction (call setup)

Before the call, the customer profile (free text/CRM dump) is converted once into structured context by two small LLM calls:

- `customer_profile_summary` → `{Name, Age, Loyalty, Gender}` (header card).
- `call_context_info` → JSON with keys `policy_info, premium, addons, claims, vehicle, customer`, using `response_format={"type": "json_object"}`, each value a readable point-form string. **[domain]** — adapt categories; the pattern that matters for cross-sell is an explicit field like:
  - `Add-ons Included: Battery Protect, Roadside Assist`
  - `Add-ons Not Included but Eligible and Recommended: Zero Dep, Return to Invoice`

That "eligible but not enrolled" list is what the generator uses as the **up-sell candidate set** — precompute it in data rather than asking the LLM to figure out eligibility live.

The concatenated context string is passed to every nudge-generation call.

---

## 6. Robust JSON handling of LLM output

Even with "JSON only" instructions, wrap parsing:

```python
def clean_json_string_curly(t):   # for objects
    s, e = t.find('{'), t.rfind('}')
    return t[s:e+1] if s != -1 and e >= s else t

def clean_json_string_square(t):  # for arrays
    s, e = t.find('['), t.rfind(']')
    return t[s:e+1] if s != -1 and e >= s else t
```

Plus: coerce dict→[dict] when a single object comes back; `str(x or "")` every field; on any parse failure return the previous state.

---

## 7. Local BERT pre-filter (optional cost/latency optimization)

`NudgeLibraryFilter` (sentence-transformers, **all-MiniLM-L6-v2**, run locally):

- Parses a markdown "Nudge Library" file into **sections** (`## **1. Title**` headers) and numbered **questions** within sections.
- Pre-computes embeddings for all sections/questions at startup.
- At runtime, embeds the transcript and ranks by cosine similarity (`similarity_threshold=0.3` default, `top_k` sections=5 / questions=10).
- Three modes for question selection: `independent` (rank all questions), `filtered` (rank only within top sections), `all` (everything from top sections).
- Purpose: shrink the library text injected into the generator prompt to just the relevant portions.

Dependencies: `sentence-transformers scikit-learn numpy torch`. Ship the model files with the app or download-once; don't hardcode a user-specific path (the original project did, and it broke portability).

---

## 8. Orchestration, models & config

- **Two Azure OpenAI deployments**: a standard model for insights/listener, a stronger "4.1" deployment for nudge generation (separate `api_version` per deployment). Generator uses `temperature=0.3`; listener/insights use default.
- Config via `.env` → env vars: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_VERSION`, `AZURE_OPENAI_MODEL`, plus `_4_1` variants; `AZURE_SPEECH_KEY/REGION` for STT; `AZURE_SEARCH_ENDPOINT/API_KEY` for RAG.
- Initial proactive nudge generation is fired **in the background at session start** (~3s observed latency) so the UI isn't blocked.
- The transcript passed to the generator is truncated to the **last ~700 tokens**, prefixed by the accumulated insight bullets (so older context survives truncation in compressed form).
- Every model call goes through a `track_model_call(response)` metrics hook capturing `prompt_tokens` / `completion_tokens` — build this in from day one.

### Observability (worth replicating)
Two log streams per session, timestamped with elapsed time:
- **Session report** — every transcript delta, every function call/return with full input/output JSON, insights, timing.
- **Nudge QC report** — only generator calls: input transcript+context vs. returned nudges, for offline quality review of recommendations.

Observed event frequency in a real session: `listening_nudges` ~47 calls, insights ~27, generator only ~14 — i.e., the flag-gating cut generator calls to ~30% of listener calls.

---

## 9. Reusable prompt-engineering lessons

1. **Word limits everywhere** ("<15 words", "10–12 words") — nudges are read aloud live; long output is useless.
2. **Few-shot GOOD/BAD contrast pairs** beat abstract rules, especially to suppress "factual summary" nudges and near-duplicate insights.
3. **Semantic dedup via "core concept extraction"** instruction + explicit duplicate examples.
4. **"Return the same text if unchanged"** (IntentCapture, CallStage) turns an LLM output into a cheap change-detector for downstream triggers.
5. **Stage-gate the selling**: enumerate call stages, and hard-forbid cross-/up-sell except in the one stage where the customer is receptive. This is the single most important guardrail for not annoying customers.
6. **Never trust the LLM to preserve items** — enforce preservation/positioning deterministically in code (§4.4).
7. **Pass "already suggested" history back in** to prevent repetition across regenerations.
8. **Fail safe**: on any parse/API error, return the previous state, never an empty UI.
9. **Split cheap-frequent from expensive-rare** LLM calls, connected by a boolean flag.

---

## 10. Minimal implementation checklist for the new project

- [ ] Define your Nudge JSON contract (Status / Nudge / SpokenFlag) and fixed list size.
- [ ] Define your call-stage enum and which stage(s) permit cross-sell/up-sell.
- [ ] Build structured customer context extraction, including an explicit "eligible-but-not-owned products" field (your cross-sell candidate set).
- [ ] Implement 4 LLM functions: proactive-init, insights (summary+intent+stage), listener (flags), generator (with post-processing merge).
- [ ] Wire the `update_flag` gate between listener and generator.
- [ ] Add JSON-cleanup helpers + fail-safe fallbacks.
- [ ] (Optional) local embedding pre-filter for a large recommendation library.
- [ ] Add per-session logging + a dedicated QC log of generator inputs/outputs.
- [ ] Track tokens/latency per call from the start.
