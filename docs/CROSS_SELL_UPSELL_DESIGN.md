# Cross-Sell / Up-Sell "Suggested Offers" — Design & Implementation
### Omnichannel-CX-Project (as shipped, 2026-07-23)

This documents the cross-sell/up-sell engine **actually implemented in this project** — the
architecture, rules, prompts, flow, and the decisions made along the way. It was designed from
the Call Agent Assist Tool's nudge engine
([Call_Agent_Assist_Tool_CROSS_SELL_UPSELL_DESIGN.md](Call_Agent_Assist_Tool_CROSS_SELL_UPSELL_DESIGN.md)),
adapted from live voice calls to **async, ticket-based omnichannel chat** with a human admin in
the loop. Where this design deliberately diverges from the reference, the divergence and its
reason are stated.

---

## 1. What the system does

When an admin opens a customer's conversation in the inbox, the right panel shows a
**"Suggested Offers"** card containing at most **2** cross-sell/up-sell recommendations for that
customer — each a short pitch grounded in the customer's own BFSI data and recent conversation,
with an explicit "Why" line. The admin **Approves** (→ an editable offer draft is created) or
**Dismisses** each. On **Send offer**, the (possibly edited) text is delivered to **every push
channel the customer has on record** (WhatsApp and/or email) — never web chat — and the sent
offer appears inside the conversation timeline as a labelled, bank-initiated touchpoint.

Nothing ever reaches a customer without two human clicks (Approve, then Send).

---

## 2. Division of labour — the core design principle

Inherited from the reference doc's hardest-won lesson ("never trust the LLM to obey rules";
its §4.4/§9.6) and this codebase's own stance (deterministic, traceable agent-assist):

| Owner | Responsibility |
|---|---|
| **Code** | *When* it's acceptable to sell (gate) · *what* is offerable (candidate rules over real data) · validating the LLM only picked from that set · dedup/one-shot memory · delivery |
| **LLM** | *Which* ≤2 candidates best fit the recent conversation · phrasing the pitch (≤20 words, citing the customer's real numbers) |
| **Admin** | Final judgment: approve/dismiss every offer; edit the text; press Send |

---

## 3. Pipeline

```
Admin opens conversation
        │
        ▼
GET /admin/agent-assist/opportunities?conversation_id=…
        │
        ├─ 1. GATE (code): latest inbound message negative? → {suppressed: reason},
        │      card shows "No offers right now — recent negative sentiment". No LLM call.
        │
        ├─ 2. CANDIDATES (code): resolve the Neo4j customer via channel identities →
        │      holdings (loans/policies/cards/accounts/FDs) + charges + recent turns →
        │      build_candidates() → list of {product, kind, basis}. Empty → empty card.
        │
        ├─ 3. LLM (GroqGenerator, temp 0.2): system prompt (rules + GOOD/BAD few-shot,
        │      JSON-only) + user prompt (profile · ALLOWED CANDIDATES · last ~10 turns ·
        │      ALREADY SUGGESTED do-not-repeat list) → JSON array of ≤2 picks.
        │
        ├─ 4. VALIDATE (code): JSON cleanup ([…] extraction, dict→[dict]); DROP any
        │      product not in the candidate set; `kind` taken from OUR candidate (never
        │      the LLM's claim); pitch/confidence clamped. Parse failure → previously
        │      stored pending rows (fail-safe: the card never blanks).
        │
        ├─ 5. PERSIST: new items → agent_assist_recommendations rows (pending), deduped
        │      by product against EVERY prior row — pending/approved/dismissed all retire
        │      a product for that conversation ("one-shot").
        │
        ▼
"Suggested Offers" card (Cross-sell / Up-sell badge · pitch · Why: <basis> · Approve/Dismiss)
        │
        ├─ Dismiss → row dismissed; product retired (feeds the do-not-repeat list)
        │
        └─ Approve → POST …/recommendations/{id}/decision
               │  guards (checked BEFORE anything changes):
               │    · customer has a whatsapp/email identity?  else 400
               │    · another draft pending on this conversation? else 409
               ▼
           reply_draft created (channel="offer", pitch as editable draft_text)
               ▼
           Green draft card: "💡 Approved offer — edit & send" → admin edits → Send offer
               ▼
           POST /admin/reply-drafts/{id}/send  →  _send_offer_draft():
             deliver the SAME text to every push identity (whatsapp and/or email;
             missing ones skipped) · email = FRESH mail, subject "An offer curated
             for you", no threading (an offer is not a reply) · ONE outbound turn
             per delivery (metadata.source="opportunity_offer") · draft → sent ·
             audit event "offer_draft_sent" with the delivery list
```

If the customer replies to the offer (email/WhatsApp), the reply enters the normal inbound
pipeline, resolves to the same customer, and lands in the same conversation — closing the loop.

---

## 4. The gate

**Single gate:** the customer's **latest inbound message must not be negative** (sentiment on the
turn's metadata). That's it.

History (all built, then removed by explicit product decision, in order):
1. ~~fraud/chargeback flag or dpd > 0~~ — dropped (BFSI addition beyond the reference).
2. ~~attrition band High~~ — dropped (same).
3. ~~open ticket in progress~~ — dropped last (it forced answer-and-resolve clicks before any
   offer could show; the admin reviewing each offer is the remaining judgment layer).

The reference doc's stage-gating survives in spirit as: *don't pitch someone who's upset* +
*a human approves everything*. `check_gates()` keeps `tickets` in its signature for easy
re-tightening.

---

## 5. Candidate rules (the "eligible-but-not-owned" set, reference §5)

`build_candidates(graph_context, segment, charges, turns)` — deterministic, one candidate per
product (first rule wins), each carrying a `basis` string with the customer's real numbers that
the LLM must cite. 10 rules:

| # | Trigger (customer's real data) | Offer | Kind |
|---|---|---|---|
| 1 | Has loan, no term/life policy | Term insurance | cross-sell |
| 2 | No health policy | Health insurance | cross-sell |
| 3 | Has account(s), no credit card | Credit card | cross-sell |
| 4 | Avg balance ≥ 5× account minimum, no FD | Fixed deposit | cross-sell |
| 5 | Avg balance ≥ 5× minimum | Premium account tier | up-sell |
| 6 | FD maturing within 90 days | FD renewal | up-sell |
| 7 | ≥ 5,000 reward points, dpd < 30 | Premium card upgrade | up-sell |
| 8 | HNI/premium/wealth segment on an entry card variant (Classic/Silver/Basic), dpd < 30 | Premium card upgrade | up-sell |
| 9 | ≥ 2 unreversed penalty charges (reversal_status not reversed/approved) | Charge-waiver account upgrade — "stop paying these ₹X" | up-sell |
| 10 | A recent turn's intent maps to a product family the customer does NOT hold (loan_status / loan_application → loan; card_management → card; policy_status → policy) | That product | cross-sell |

Rule 10 is the purest "based on the recent conversation" signal — the customer *asked* about it.
Its coverage is limited by the intent taxonomy: FD/insurance questions classify as
`general_inquiry` and cannot be mapped; and family granularity is coarse (holding ANY policy
blocks a policy-interest match). Both are documented limitations.

**Deliberately rejected rules:** age/occupation demographics (profiling without outcome data),
loan pre-approvals (no credit-scoring data), card limit increases (invented threshold),
premium-due-as-offer (duplicates the Profile Snapshot's Upcoming-event tile).

The rule list is open-ended — each new bank product = one more ~6-line rule appended here.

---

## 6. The LLM call

One call per generation (no listener/generator split — see §9). `GroqGenerator._generate`
(llama-3.1-8b-instant, temperature 0.2), operation `opportunity_generation` so every call lands
in the existing LLM-observability pipeline automatically.

**System prompt rules** (reference §9 lessons applied):
1. Pick AT MOST 2, ONLY from the ALLOWED CANDIDATES list — never invent an offer.
2. Prefer candidates connected to the recent conversation.
3. One sentence, ≤ 20 words, MUST cite the real numbers from the candidate's basis.
4. Never repeat/paraphrase the ALREADY SUGGESTED list.
5. Empty array beats weak offers.
6. JSON array only — `[{product, kind, pitch, reason, confidence}]`.
Plus GOOD/BAD few-shot contrast pairs (grounded-numbers pitch vs. generic-marketing pitch vs.
out-of-candidates pitch).

**User prompt sections:** customer profile + holdings counts · ALLOWED CANDIDATES (with basis) ·
RECENT CONVERSATION (last ~10 turns, oldest first, 200 chars/turn) · ALREADY SUGGESTED.

**Known caveat:** the pitch *wording* can embellish beyond the basis (observed live: an invented
"12.99% interest"). Product and eligibility are code-validated; wording is not — the admin's
edit-before-send is the control. A stricter numbers-only post-check was considered and deferred.

---

## 7. Storage, dedup, decisions

- Reuses the existing `agent_assist_recommendations` table (no migration):
  `action_type` = `cross_sell` | `up_sell` (the `UP_SELL` enum value was added),
  `reason` = the pitch, `metadata` = `{product, basis, why_now, source:"opportunity_engine"}`.
- **One-shot per conversation:** a product ever suggested there (any status) is never suggested
  again. Re-runs show an empty card until a NEW grounded trigger appears (e.g. rule 10 from a
  fresh product question). No expiry window (deferred).
- Approve/Dismiss uses the existing decision endpoint + audit events; **approve additionally
  creates the offer draft** (the whole point — the old NBA "Approve records a decision and does
  nothing" pattern was explicitly rejected).

---

## 8. Delivery — offers are push messages

Real banks send offers where the customer will actually see them: WhatsApp and email. So:

- An offer draft (`channel="offer"`) delivers to **every** push identity on record — both when
  both exist, the one that exists otherwise. **Web chat is never used** (no push; an offer parked
  in an unopened portal isn't sent in any meaningful sense).
- Email goes as a **fresh** mail ("An offer curated for you"), not a threaded reply.
- One outbound turn is persisted **per delivery** (`metadata.source="opportunity_offer"`), so the
  timeline and audit show exactly what went where.
- Approve fails cleanly (400) for a customer with no push identity at all.

---

## 9. UI

- **Right panel — "Suggested Offers" card:** items with a Cross-sell (green) / Up-sell (amber)
  badge, the pitch, a "Why: <basis>" grounding line, Approve/Dismiss. Suppressed/empty states
  say "No offers right now[ — reason]". (The old rule-based "Recommended actions" NBA card was
  removed as redundant — its backend engine/endpoint remain API-only.)
- **Offer draft card:** green variant of the HIL draft card — "💡 Approved offer — edit & send",
  "Delivers via WhatsApp + Email", button "Send offer".
- **Conversation timeline — offer labelling + glue grouping:** a sent offer renders as a
  **bank-initiated** touchpoint, and it is *transparent to grouping*: an offer never starts its
  own request and never splits a ticket. The request that triggered the offer, the offer itself,
  and the customer's reply-to-offer render as **ONE request** —
  - *Detailed view:* a "Bank-initiated / Offer Message" row (amber Offer pill) between the
    normal query→reply rows;
  - *Lineage view:* one row whose mini-timeline gains an amber-ringed "Offer · <channel>" dot
    between the conversation dots.

---

## 10. Differences from the reference design (and why)

| Reference (live call) | Here (async chat) | Why |
|---|---|---|
| Rolling STT transcript, listener LLM on every utterance, `update_flag` gate to the generator | One generation when the admin opens the conversation | No live transcript; the admin panel load is the natural trigger; gates short-circuit before any LLM call |
| Exactly 3 rolling nudges with SpokenFlag/Status lifecycle | ≤ 2 one-shot offers with pending/approved/dismissed lifecycle | Offers are discrete approvals, not live talking points |
| Call-stage enum gates the selling (LLM-classified) | Sentiment-only gate (code) + human approval | Stage ≈ ticket/conversation state here; after iteration the human reviewer was chosen as the main guardrail |
| Nudges spoken by the agent | Offer text delivered to the customer's push channels after human edit | Async channels; two-click safety |
| Two Azure OpenAI deployments, BERT library pre-filter | One Groq model, no pre-filter | Single-LLM infra; candidate set is small (10 rules), nothing to pre-filter |
| LLM-preservation merge algorithm | Not needed (no list to preserve); instead: candidate-set validation + kind override | Same "never trust the LLM" lesson, different enforcement point |

**Kept from the reference:** eligible-but-not-owned candidate set precomputed in data (§5) ·
already-suggested do-not-repeat history (§9.7) · JSON cleanup + fail-safe-to-previous-state
(§6/§9.8) · word limits + GOOD/BAD few-shot (§9.1–2) · grounding numbers in the pitch ·
token/latency tracking on every call (via the project's existing LLM observability).

---

## 11. Code map

| Piece | Location |
|---|---|
| Engine (gate · candidates · prompt · validation) | `services/agent_assist_service/opportunity_engine.py` |
| API: generation + persist/dedup; Approve → offer draft | `apps/api/routes/agent_assist.py` (`GET /admin/agent-assist/opportunities`, decision endpoint) |
| Dual-channel offer send | `apps/api/routes/reply_drafts.py` (`_send_offer_draft`) |
| Schema (`UP_SELL`) | `shared/schemas/agent_assist.py` |
| Repository getter | `services/persistence_service/repository.py` (`get_agent_assist_recommendation`) |
| UI: card, offer draft, labelling, glue grouping | `apps/admin-ui/app.js` + `style.css` |
| Tests (LLM mocked; gates, every rule, validation, approve→send flow) | `tests/test_opportunities.py` |
| Manual test scenarios | `docs/hil-test-questions.md` (Sayantini Group 4, Fathima Group 5) |
| Session-by-session change history | `docs/Sayantini-session-changes-log.md` (Fix 42–42f) |

## 12. Verified behaviour (live, real data)

End-to-end on the seeded customer Sayantini (`CRN00010001`), fully organic: portal question
"What are your personal loan interest rates?" → rule 10 (asked-about-loans, holds none) + rule 9
(her real ₹3,791 AnnualFee+LateFee charges) → two grounded items in the card → Approve → offer
draft → Send → delivered to email only (she has no WhatsApp identity — skip-missing verified) →
Mailpit mail → she replied to the offer email → reply landed in the same conversation, same
ticket → the whole chain rendered as ONE request (question → offer → reply). Suppression
verified live on negative-sentiment and (before its removal) open-ticket states.
