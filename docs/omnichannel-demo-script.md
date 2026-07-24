# Omnichannel Demo Script

Purpose: demonstrate the **omnichannel ideology** — one customer = one identity = one continuous
conversation across channels, with correct ticket continuity (merge a continuation, fork a genuinely
new matter). Two customers, run separately.

**Portal mechanics:** Web Chat = the "Chat with support" box · WhatsApp / Email = the
"Submit a request" form (pick the channel there). Send each message as the **logged-in customer**.

**Before you start:** fresh-reseeded DB (empty inbox, 5 BFSI customers), all fixes live. Keep three
tabs open — Admin UI (`/admin-ui`), Portal, Mailpit (`:8025`).

**Two ordering rules (both customers):**
- Send the **negative/exit message LAST** (Seq 5) — otherwise it gates the offer card in Seq 4.
- Run one customer fully, then the other — separate conversations, cleaner Lineage screenshots.

**Small-LLM caveat:** a Seq-2 opener (#4) must classify as a dispute/complaint (L2) to open a
ticket. If it auto-answers instead, resend a firmer version ("I want to **formally raise a
ticket / dispute**…") — else there's no ticket for the next messages to continue.

**Continuity caveat (important — keep the topic word consistent):** ticket continuity matches
follow-ups to an open ticket *within the same intent*. Keep the same topic word across all turns of
a Seq-2 sequence ("dispute"/"disputed transaction" for a dispute; "claim CLM…" for a claim). A
strongly-reworded follow-up that reads as a status question ("any update?", "has this been sorted?")
or a "complaint" can classify as a *different* intent and fork into a second ticket. This is upstream
small-LLM intent instability, not the continuity engine. **Known next step:** cross-intent continuity
(the LLM referee matching across intents) so natural rephrasing is handled — deferred.

---

## Capabilities being demonstrated

1. **Identity convergence** — email, phone, web-chat all resolve to one customer → one conversation.
2. **Cross-channel ticket continuity** — a request started on one channel, continued on another,
   stays ONE ticket (scope refinement + LLM referee).
3. **Correct fork** — a genuinely different matter gets its own ticket, even same intent/customer.
4. **Cross-channel response + offer delivery** — agent reply / offer goes out on the right channel(s).
5. **Whole-customer intelligence** — attrition computed over the entire cross-channel history.

---

# Customer: Sayantini Sarkar

`CRN00010001` · `sayantini.s.55@gmail.com` · `7890864700`
Data: Classic card ₹10.65L limit (dpd 45) · FD (matures 2028) · Health policy · no loans · ~₹3,791 charges.

### Seq 1 — Identity convergence (3 channels → 1 conversation)
| # | Channel | Message |
|---|---------|---------|
| 1 | WhatsApp | What is my credit card limit? |
| 2 | Email | When is my FD maturity date? |
| 3 | Web Chat | What are your customer support working hours? |

**Check:** ONE conversation ("Sayantini Sarkar"), three channel-coloured turns, all auto-answered,
no tickets. Portal chat box shows only #3.

### Seq 2 — Cross-channel ticket continuity (centrepiece)
| # | Channel | Message |
|---|---------|---------|
| 4 | Email | I want to dispute a transaction on my last statement. |
| 5 | Web Chat | It's the Rs. 4,500 charge at TechMart on my Mastercard Classic card. |
| 6 | Email | Any update on my dispute? This is urgent for me. |

**Check:** #4 opens a ticket; #5 **refines the same ticket** (reply references the card details);
#6 **stays on the same ticket** (LLM referee). **Open Tickets = 1.** Lineage = one request row with
email · web · email dots.

### Seq 3 — Negative control (correct fork)
| # | Channel | Message |
|---|---------|---------|
| 7 | WhatsApp | I also want to dispute a UPI payment of Rs. 900 I never made. |

**Check:** **Open Tickets = 2** — a separate UPI ticket. Merge and don't-merge both proven.

### Seq 4 — Cross-channel response + offer delivery
| # | Channel | Action / Message |
|---|---------|------------------|
| 8 | admin | Open her held dispute draft → edit → **Send** |
| 9 | Web Chat | What are your personal loan interest rates? I'm thinking about applying. |
| 10 | admin | Approve the Suggested Offer → edit pitch → **Send offer** |
| 11 | Email | *(reply to the offer mail)* I'm interested, tell me more. |

**Check:** #8 reply reaches the customer on-channel; #9 fires the offer card; #10 pushes to her
channels — now **once per channel** (dedupe fix); #11 **glues into the same request** as the offer.

### Seq 5 — Whole-customer attrition
| # | Channel | Message |
|---|---------|---------|
| 12 | Email | If this isn't fixed I will close my account and switch banks. |

**Check:** Attrition band flips **High** with reasons — over her whole cross-channel history.

---

# Customer: Fathima Devasahayam

`CRN00010005` · `fathimawork511@gmail.com` · `7538870992`
Data: SA `…007` (avg ₹5,447) · SA `…008` (avg ₹1,721, below-min) · Personal Loan `LN001002`
(dpd 15, penalty ₹2,371) · Term + Auto policies · 3 claims (theft/under-review/approved) ·
charges ₹828 + ₹265 · no card, no FD.
**⚠ Her email/WhatsApp are real — safe here (local Mailpit + WhatsApp test mode); verify delivery
mode before any non-local run.**

### Seq 1 — Identity convergence
| # | Channel | Message |
|---|---------|---------|
| 1 | WhatsApp | What is the status of my Personal Loan LN001002? |
| 2 | Email | What is the current balance of my savings account 40900000100007? |
| 3 | Web Chat | When is the next premium due on my Term Insurance policy? |

**Check:** ONE conversation, grounded auto-answers, no tickets.

### Seq 2 — Cross-channel ticket continuity (her account-charge matter)
| # | Channel | Message |
|---|---------|---------|
| 4 | Email | I want to dispute a charge on my account 40900000100008. |
| 5 | Web Chat | It's the Rs. 265 minimum balance charge — please dispute it. |
| 6 | WhatsApp | Any update on my charge dispute? |

**Check:** #4 opens a ticket; #5 refines it (account/amount details); #6 **stays on the same ticket**
cross-channel. **Open Tickets = 1.** Lineage = one request row with email · web · WhatsApp dots.

> ✅ **Verified (24 Jul).** Reuse the same topic word ("dispute"/"charge") in all three turns so they
> classify as one intent and continuity holds — varying it (e.g. "complaint" then "penalty update")
> forks into separate tickets (intent instability, deferred).

### Seq 2b — Continuity on a different topic (her theft claim `CLM001013`, Processing)
| # | Channel | Message |
|---|---------|---------|
| 4 | Email | I want to raise a ticket about my theft claim CLM001013. |
| 5 | Web Chat | The claim CLM001013 for the stolen items is still Processing — I need it escalated. |
| 6 | WhatsApp | Any update on my claim CLM001013? |

**Check:** one claim ticket across all three channels (**Open Tickets = 1**), under a CLAIM theme —
shows continuity works across topics, not just disputes. Keep "claim CLM001013" in every turn.

### Seq 3 — Negative control (different matter → fork)
| # | Channel | Message |
|---|---------|---------|
| 7 | Email | Separately, the overdue penalty of Rs. 2,371 on my loan LN001002 is too high — please waive it. |

**Check:** **Open Tickets = 2** — the loan-penalty matter is its own ticket, not merged into the
account-charge one.

### Seq 4 — Cross-channel response + offers (richest offer customer)
| # | Channel | Action / Message |
|---|---------|------------------|
| 8 | admin | Open a held draft → edit → **Send** |
| 9 | Web Chat | Thanks, that's all sorted now. By the way, how do I apply for a credit card? |
| 10 | admin | Approve a Suggested Offer (credit card / health insurance) → edit → **Send offer** |

**Check:** #9 clears the sentiment gate *and* triggers rule-10; offer card shows 1–2 items; offer
turn labelled in Lineage.

### Seq 5 — Whole-customer attrition
| # | Channel | Message |
|---|---------|---------|
| 11 | WhatsApp | I'm thinking of switching banks — nothing here works for me. |

**Check:** Attrition band → **High** (exit-language override), independent of channel.

---

# Customer: Digvijay Yadav

`CRN00010003` · `digvijayyadav48@gmail.com` · `7700920746`
Data: SA `40900000100004` (avg ₹2,508, **below-min**) · SA `40900000100005` (avg ₹14,624) ·
FD `FD001003` (Matured) · Home Insurance `POL001004` (premium due 2026-09-01) · 3 structural-damage
claims: `CLM001008` Approved · `CLM001009` Rejected · `CLM001010` Processing · MinBalance charge
₹658.56 (Charged) · **no card, no loan** · Segment Affluent.

### Seq 1 — Identity convergence
| # | Channel | Message |
|---|---------|---------|
| 1 | WhatsApp | What is the balance of my savings account 40900000100005? |
| 2 | Email | When did my fixed deposit FD001003 mature? |
| 3 | Web Chat | What are your customer support working hours? |

**Check:** ONE conversation, grounded auto-answers, no tickets.

### Seq 2 — Cross-channel ticket continuity (his stuck UPI payment)
| # | Channel | Message |
|---|---------|---------|
| 4 | Email | I made a UPI payment of Rs. 41,224 to Romil Halder but the money was debited and never credited. I want to dispute this transaction. |
| 5 | Web Chat | About my disputed transaction — it's the Rs. 41,224 UPI payment to Romil Halder that got debited but not credited. |
| 6 | WhatsApp | Any update on my disputed transaction for the Rs. 41,224 UPI payment? |

**Check:** one transaction-dispute ticket across all three channels (**Open Tickets = 1**), grounded
in his real stuck txn `TXN0001000045`. ✅ **Verified 4/4** (all turns stay `transaction_dispute`).
Keep "disputed transaction" / "dispute" in every turn — see the continuity caveat below.

### Seq 3 — Negative control (different matter → fork)
| # | Channel | Message |
|---|---------|---------|
| 7 | Email | Separately, please explain the Rs. 658 minimum balance charge on account 40900000100004. |

**Check:** **Open Tickets = 2** — the charge matter is its own ticket, not merged into the claim one.

### Seq 4 — Cross-channel response + offers
| # | Channel | Action / Message |
|---|---------|------------------|
| 8 | admin | Open a held draft → edit → **Send** |
| 9 | Web Chat | Thanks, that's sorted. By the way, how do I apply for a credit card? |
| 10 | admin | Approve a Suggested Offer (credit card / health insurance) → edit → **Send offer** |

**Check:** #9 clears the sentiment gate + triggers rule-10 (holds no card); offer card shows 1–2
items; offer turn labelled in Lineage.

### Seq 5 — Whole-customer attrition
| # | Channel | Message |
|---|---------|---------|
| 11 | WhatsApp | I'm done with this bank, I want to close my accounts and leave. |

**Check:** Attrition band → **High** (exit-language override), independent of channel.

---

## Known caveats (small-LLM / pre-existing, not omnichannel bugs)

- A detail-less opener can pull an **irrelevant KB paragraph** into the answer (e.g. loan info in a
  dispute reply). Answer wording is non-deterministic; product/eligibility grounding is enforced,
  free-text is not.
- Email-channel replies may greet the **email username** ("Sayantini S 55") rather than the real
  name — name propagation gap on the email path.
- Offer pitch **wording** can embellish numbers (admin edit-before-send is the control).
- Seq-2/L2 outcomes vary with the small LLM's per-query level call.
