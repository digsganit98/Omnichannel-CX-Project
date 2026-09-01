from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from services.crm_service.client import CRMClient
from services.persistence_service.repository import CXRepository
from services.pii_service.masker import mask_text
from services.ticket_service.assignment import assign_team
from services.ticket_service.priority_scoring import score_priority
from services.workflow_service.approvals import requires_approval
from services.workflow_service.sla import sla_hours
from shared.schemas.intents import Intent, Urgency
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket, TicketStatus
from shared.utils.ids import new_id


class TicketManager:
    def __init__(self, repository: CXRepository, crm: CRMClient | None = None, generator=None,
                 neo4j_client=None) -> None:
        self.repository = repository
        self.crm = crm or CRMClient()
        # Optional LLM used only by the tier-4 ticket referee (_referee_match).
        # Deliberately no default instance: without a generator the referee is
        # skipped and unmatched messages open a new ticket (pre-referee behavior).
        self.generator = generator
        # Optional graph client, used only to keep a resolved ticket's status in step with
        # the graph copy. Optional so every existing caller keeps working untouched.
        self.neo4j_client = neo4j_client

    def create_or_get_ticket(
        self,
        conversation_id: str,
        customer_id: str,
        message: InboundMessage,
        intent: Intent,
        urgency: Urgency,
        escalation_reason: str | None = None,
        customer: dict | None = None,
        sentiment: str = "neutral",
        graph_context: dict | None = None,
        hold_required: bool = True,
    ) -> Ticket:
        """Get the ticket this message belongs to, creating one if it is a new matter.

        ``hold_required`` decides the STATUS, not whether a ticket exists (Phase 4 of the
        ticket-model redesign): False means a LOGGED thread - a grouping id nobody is
        working - and True means OPEN, a case a human is on. It defaults to True so any
        caller that has not been updated keeps producing serviceable tickets exactly as
        before, rather than silently creating invisible ones.
        """
        ticket_scope = _ticket_scope(intent.value, message.text, escalation_reason, graph_context)
        existing = (
            self.repository.find_active_ticket_for_scope(conversation_id, intent.value, ticket_scope)
            if ticket_scope
            else self.repository.find_active_ticket_for_intent(conversation_id, intent.value)
        )
        if not existing and ticket_scope and ticket_scope != f"{intent.value}:other":
            # Omnichannel continuation: a vague opener ("dispute a transaction") gets the
            # ":other" fallback scope; when the customer then supplies specifics ("on my
            # Mastercard"), the specific scope must REFINE that open ticket, not fork a
            # duplicate. Only ":other" is upgraded — two specific scopes (card vs upi)
            # are genuinely distinct incidents and still get separate tickets.
            #
            # But "vague ticket open + specific message arrived" is NOT proof the two are
            # the same matter. Live example: a dispute ticket sat at ":other" (the customer's
            # IMPS details did not match any scope keyword), then "I ALSO have a problem with
            # a UPI payment" arrived — a second, separate complaint — and this rule absorbed
            # it into the first ticket's description as "[Details added: ...]". The complaint
            # stopped existing as its own item, with no error and nothing visibly wrong: the
            # silent-merge failure the referee below was built to prevent.
            #
            # So the referee gets a VETO here — not a vote. It can block a merge it judges to
            # be a different matter, but it is never a precondition: when no generator is
            # configured, or the call fails, refinement proceeds exactly as before. Making
            # the referee a precondition would silently disable refinement whenever the LLM
            # is unavailable, turning a deterministic behaviour into an LLM-dependent one.
            fallback = self.repository.find_active_ticket_for_scope(
                conversation_id, intent.value, f"{intent.value}:other"
            )
            if fallback and not self._referee_rejects(fallback, message):
                existing = self._refine_ticket_scope(fallback, ticket_scope, message)
        if not existing and ticket_scope:
            # Tier-4 omnichannel referee: the scope label didn't string-match any
            # active ticket (e.g. a vague "any update on my dispute?" follow-up
            # arriving on another channel after the ticket was refined to :card).
            # Labels can't answer "same matter or new matter?" — ask the LLM to
            # pick among the CODE-VETTED candidates or say NEW. Any doubt/error/
            # absent-LLM ⇒ new ticket: a spurious fork is visible and fixable; a
            # spurious merge corrupts the record silently.
            #
            # Candidates are NOT filtered by the incoming intent. Filtering by it excluded
            # the commonest follow-up there is: "any update on my dispute?" classifies as
            # ticket_status, so a transaction_dispute ticket was never a candidate, the
            # referee never ran, and the question opened a brand-new ticket about asking
            # after a ticket. Relatedness is a judgement about the text — which is exactly
            # what the referee reads — not about two intent labels being equal.
            candidates = self.repository.list_active_tickets_for_conversation(conversation_id)
            if candidates:
                existing = self._referee_match(candidates, message)
        if existing:
            # PROMOTION: a logging thread becomes serviceable the first time any message on
            # it needs a person. This is the "logged -> open" transition the redesign is
            # built around, and it is one-way: nothing here ever demotes an open ticket back
            # to logged, because a human being done is a separate decision (closing it).
            if hold_required and existing.status == TicketStatus.LOGGED:
                self.repository.update_ticket(
                    existing.ticket_id, status=TicketStatus.OPEN.value
                )
                self.repository.add_ticket_event(
                    existing.ticket_id, "ticket_promoted", "orchestration",
                    {"from": TicketStatus.LOGGED.value, "to": TicketStatus.OPEN.value,
                     "escalation_reason": escalation_reason},
                )
                self._mirror_status_to_graph(existing, TicketStatus.OPEN.value)
                # Re-read through _ticket(): update_ticket returns a RAW row (metadata_json,
                # priority_breakdown_json), not the model's field shape.
                # A promoted ticket is now real work, so it also reaches Jira - which it
                # never did while it was logged (sync_ticket skips those).
                existing = self.sync_ticket(existing.ticket_id, customer=customer)
            # This message just landed on an existing thread. Record it as ACTIVITY so the
            # referee's candidate list can rank by "last touched" (migration 018).
            #
            # This is the exact spot where the old model lost that fact: the function
            # returned here without writing anything, so a ticket could receive messages
            # for days while every timestamp on it stayed frozen at creation. Deliberately
            # not update_ticket() - that would move updated_at, which analytics reads as
            # the close time.
            self.repository.touch_ticket_activity(existing.ticket_id)
            return existing
        priority, breakdown = score_priority(intent, urgency, sentiment, graph_context)
        ticket = Ticket(
            ticket_id=new_id("tkt"),
            conversation_id=conversation_id,
            customer_id=customer_id,
            title=message.subject or f"{intent.value.replace('_', ' ').title()} request",
            description=message.text,
            intent=intent.value,
            priority=priority,
            assigned_team=assign_team(intent.value),
            # Phase 4: no hold -> a LOGGED grouping id; a hold -> an OPEN case.
            status=TicketStatus.OPEN if hold_required else TicketStatus.LOGGED,
            approval_status="pending" if requires_approval(intent.value) else "not_required",
            escalation_reason=escalation_reason,
            sla_due_at=datetime.now(timezone.utc) + timedelta(hours=sla_hours(priority.value)),
            priority_score=breakdown.total,
            priority_breakdown=breakdown.model_dump(),
            metadata={
                "channel": message.channel.value,
                "provider": message.provider,
                "ticket_scope": ticket_scope,
            },
        )
        self.repository.create_ticket(ticket)
        self.repository.add_ticket_event(
            ticket.ticket_id,
            "ticket_created",
            "orchestration",
            {"intent": intent.value, "priority": priority.value, "escalation_reason": escalation_reason},
        )
        return self.sync_ticket(ticket.ticket_id, customer=customer)

    def _refine_ticket_scope(self, ticket: Ticket, new_scope: str, message: InboundMessage) -> Ticket:
        """Upgrade an ':other'-scoped ticket to a specific scope when details arrive (any channel)."""
        metadata = {**ticket.metadata, "ticket_scope": new_scope}
        # Append the newly-supplied details to the ticket description. The original
        # description is frozen at the vague opener ("please help with a dispute");
        # without this, the ticket's own text never mentions the specifics that
        # arrived later (merchant/amount), leaving the referee and the admin UI
        # matching against a summary that omits its own defining facts.
        detail = (message.text or "").strip()
        new_desc = ticket.description
        if detail and detail not in (ticket.description or ""):
            new_desc = f"{ticket.description}\n[Details added: {detail[:500]}]"
        updated = self.repository.update_ticket(
            ticket.ticket_id, metadata_json=json.dumps(metadata), description=new_desc
        )
        details = {
            "previous_scope": ticket.metadata.get("ticket_scope"),
            "new_scope": new_scope,
            "channel": message.channel.value,
            "detail_text": message.text[:500],
        }
        self.repository.add_ticket_event(ticket.ticket_id, "ticket_scope_refined", "orchestration", details)
        self._audit(ticket, "ticket_scope_refined", details)
        return Ticket(**updated)

    def _referee_rejects(self, ticket: Ticket, message: InboundMessage) -> bool:
        """True only when the LLM RAN and judged this a SEPARATE matter from a vague ticket.

        This asks a different question from _referee_match, and needs its own prompt.
        _referee_match compares two *specific* matters ("is this the same transaction as
        the one in that ticket?"). Here the ticket is by definition vague — it is the
        ":other" scope precisely because it names no transaction, merchant or amount — so
        that question cannot be answered sensibly: "does this message describe something
        different from a ticket that describes nothing?" is trivially yes, which vetoed
        every legitimate refinement. (Observed live: a vague dispute opener followed by
        "It was the Rs.28,991 IMPS transfer to Kimaya Seth" — plainly the missing details —
        was rejected as NEW.)

        The right question is about the customer's INTENT in sending it: are they filling
        in the details of the matter they just raised, or raising an additional one?

        Deliberately asymmetric with _referee_match: that one treats "could not decide" as
        "no match" (safe, because the fallback is a new ticket). Here the fallback is an
        existing, working refinement, so "could not decide" must mean "do not block" —
        otherwise an absent or failing LLM would quietly switch refinement off.
        """
        if not self.generator:
            return False
        try:
            masked_text, _ = mask_text(message.text)
            masked_desc, _ = mask_text((ticket.description or "")[:300])
            result = self.generator._generate(
                system_prompt=(
                    "A customer raised a support issue but described it only vaguely. A newer "
                    "message from the same customer contains specific details.\n"
                    "Decide which of these it is:\n"
                    "SAME — the message supplies the missing specifics of the issue they already "
                    "raised (the transaction, merchant, amount, card or account they meant).\n"
                    "SEPARATE — the message raises an ADDITIONAL, different issue. Wording such as "
                    "\"I also\", \"another\", \"a second\", \"besides that\", or a second distinct "
                    "problem alongside the first, indicates SEPARATE.\n"
                    "When in doubt answer SAME: the vague issue has no details yet, so specifics "
                    "usually belong to it.\n"
                    "Reply with exactly one word: SAME or SEPARATE."
                ),
                user_prompt=(
                    f'The vaguely-described open issue: "{masked_desc}"\n\n'
                    f'The newer message: "{masked_text}"\n\n'
                    "Answer SAME or SEPARATE."
                ),
                operation="ticket_refine_referee",
            )
            if not result.get("llm_used"):
                return False
            verdict = (result.get("text") or "").strip().upper()
            rejected = verdict.startswith("SEPARATE")
            if rejected:
                self._audit(ticket, "ticket_refine_rejected", {
                    "ticket_id": ticket.ticket_id,
                    "verdict": verdict[:40],
                    "detail_text": message.text[:200],
                })
            return rejected
        except Exception:
            return False

    def _referee_match(self, candidates: list[Ticket], message: InboundMessage) -> Ticket | None:
        """Ask the LLM whether an unmatched message refers to an open ticket or a new matter.

        The LLM only ever picks from the code-vetted candidate list; any other
        answer, a parse miss, an LLM failure, or no generator at all returns
        None (=> caller opens a new ticket — the safe default).
        """
        if not self.generator:
            return None
        by_id = {t.ticket_id: t for t in candidates}
        try:
            masked_text, _ = mask_text(message.text)
            lines = []
            for i, t in enumerate(by_id.values(), 1):
                masked_desc, _ = mask_text((t.description or "")[:300])
                opened = t.created_at.strftime("%d %b %Y") if t.created_at else "unknown date"
                subtype = _scope_label(t.metadata.get("ticket_scope"), t.intent)
                lines.append(f'{i}. {t.ticket_id} — {subtype} (opened {opened}): "{masked_desc}"')
                # What has actually been said on this case, not just how it opened.
                # `description` is frozen at the first message, so a case that has since
                # gained a merchant, an amount and a date still reads as empty here — and
                # the rule below says to answer NEW when the message names a different
                # merchant or amount "than any open ticket". Nothing differs from nothing,
                # so every follow-up that added detail forked a duplicate. The graph has
                # linked each message to its ticket since Fix 73 ((:Ticket)-[:HAS_MESSAGE]->
                # (:Interaction)) and get_case_messages already reads exactly that — it was
                # only ever wired to the UI. Returns [] when Neo4j is unavailable, so the
                # referee falls back to the description-only behaviour rather than failing.
                for msg in _case_messages(self.neo4j_client, t.ticket_id):
                    masked_msg, _ = mask_text((msg.get("message") or "")[:160])
                    if masked_msg.strip():
                        lines.append(f"     · {masked_msg}")
            result = self.generator._generate(
                system_prompt=(
                    "You decide whether a customer's new message is a follow-up to one of their "
                    "existing open support tickets, or a brand-new separate matter.\n"
                    "Answer with a ticket id ONLY when the message clearly continues that same "
                    "specific matter — e.g. asking for its status/update, adding details to it, or "
                    "referring to the same transaction, merchant, account, or amount already in that "
                    "ticket (possibly from a different channel).\n"
                    "Answer NEW when the message describes a DIFFERENT transaction, merchant, "
                    "account, or amount than any open ticket — even if it is the same general kind "
                    "of issue (e.g. another dispute about a different charge is NEW, not a follow-up).\n"
                    "When unsure, answer NEW. Reply with exactly one ticket id from the list, or the "
                    "word NEW — no other words."
                ),
                user_prompt=(
                    "Open tickets for this customer's conversation (each shown as: id — subtype "
                    "(opened date): description). The subtype (e.g. 'card', 'upi') identifies which "
                    "specific matter the ticket is about — use it to match:\n"
                    + "\n".join(lines)
                    + "\n\nExamples:\n"
                    '- "Any update on my dispute? This is urgent." -> the matching ticket id '
                    "(a status follow-up on the existing matter)\n"
                    '- "What about the card charge at TechMart?" -> the ticket whose subtype is the '
                    "card dispute (refers to that same matter)\n"
                    '- "I want to dispute another charge - my gym billed me twice this month." -> '
                    "NEW (a different merchant/charge, so a separate matter)\n\n"
                    f'New customer message: "{masked_text}"\n\n'
                    "Answer with exactly the ticket id it continues, or NEW."
                ),
                operation="ticket_referee",
            )
            if not result.get("llm_used"):
                return None
            answer = (result.get("text") or "").strip()
            # Exact-membership validation: accept only a vetted candidate id.
            matched = next((tid for tid in by_id if tid.lower() in answer.lower()), None)
            if not matched:
                return None
            ticket = by_id[matched]
            details = {
                "matched_ticket": matched,
                "candidate_ids": list(by_id),
                "channel": message.channel.value,
                "detail_text": message.text[:200],
            }
            self.repository.add_ticket_event(matched, "ticket_referee_attached", "orchestration", details)
            self._audit(ticket, "ticket_referee_attached", details)
            return ticket
        except Exception:
            return None

    def sync_ticket(self, ticket_id: str, customer: dict | None = None) -> Ticket:
        ticket = self._ticket(ticket_id)
        # A LOGGED ticket is a grouping id for a question that needed no human, so there is
        # nothing for anyone to work in Jira. Under the ticket-model redesign every customer
        # query gets one (~10 tickets -> ~40+), so without this filter "what is my card
        # limit?" would raise a Jira issue for a question answered instantly.
        #
        # The filter is HERE, at the sync boundary, rather than at the create call site:
        # sync_ticket has two callers (create_or_get_ticket and the admin re-sync route),
        # and a logging ticket must not reach Jira through either. The record still exists
        # in our own store, so a future logging/monitoring system can read it (decision 2).
        if ticket.status == TicketStatus.LOGGED:
            self.repository.add_ticket_event(
                ticket_id, "crm_sync_skipped", "crm_integration",
                {"reason": "logged_ticket_not_serviceable"},
            )
            return ticket
        result = self.crm.create_ticket(ticket, customer)
        updates = {
            "crm_sync_status": result.status,
            "crm_sync_error": result.error,
        }
        if result.status == "synced":
            updates["external_ticket_id"] = result.data.get("external_ticket_id")
            updates["external_ticket_url"] = result.data.get("external_ticket_url")
        updated = self.repository.update_ticket(ticket_id, **updates)
        self.repository.add_ticket_event(
            ticket_id,
            "crm_sync_" + result.status,
            "crm_integration",
            {"error": result.error, **result.data},
        )
        self._audit(ticket, "ticket_crm_sync_" + result.status, {"error": result.error, **result.data})
        return Ticket(**updated)

    def add_comment(self, ticket_id: str, comment: str, actor: str = "admin") -> dict:
        ticket = self._ticket(ticket_id)
        result = (
            self.crm.add_comment(ticket.external_ticket_id, comment)
            if ticket.external_ticket_id
            else None
        )
        details = {
            "comment": comment,
            "crm_sync_status": result.status if result else "local_only",
            "crm_sync_error": result.error if result else None,
        }
        event = self.repository.add_ticket_event(ticket_id, "comment_added", actor, details)
        self._audit(ticket, "ticket_comment_added", details)
        return event

    def update_status(self, ticket_id: str, status: TicketStatus, actor: str = "admin") -> dict:
        ticket = self._ticket(ticket_id)
        result = (
            self.crm.update_ticket_status(ticket.external_ticket_id, status.value)
            if ticket.external_ticket_id
            else None
        )
        updated = self.repository.update_ticket(ticket_id, status=status.value)
        self.repository.add_ticket_event(
            ticket_id,
            "status_updated",
            actor,
            {
                "status": status.value,
                "crm_sync_status": result.status if result else "local_only",
                "crm_sync_error": result.error if result else None,
            },
        )
        # Mirror the status onto the graph copy. Without this the Ticket node keeps
        # status 'open' forever, and get_open_cases (which reads the GRAPH, not SQLite)
        # keeps feeding a closed case to the model as trusted context — so a customer
        # asking "anything pending?" after resolution would still be told their dispute
        # is open. Best-effort: a graph failure must never block resolving a ticket.
        self._mirror_status_to_graph(ticket, status.value)
        self._audit(ticket, "ticket_status_updated", {"status": status.value})
        return updated

    def _mirror_status_to_graph(self, ticket: Ticket, status: str) -> None:
        """Copy a ticket's status onto its graph node.

        get_open_cases reads the GRAPH, not SQLite, and hands the result to the reply
        generator as trusted context. A status change that does not reach the node means
        the model is told about a case whose state is stale - which is how a resolved
        dispute kept being reported as open. Best-effort by design: a graph failure must
        never block the SQLite write that already succeeded.
        """
        if self.neo4j_client is None:
            return
        try:
            from services.neo4j_service import writer as neo4j_writer
            neo4j_writer.upsert_ticket_node(
                self.neo4j_client,
                ticket_id=ticket.ticket_id,
                customer_id=self._graph_customer_id(ticket),
                intent=ticket.intent or "",
                priority=ticket.priority.value if hasattr(ticket.priority, "value") else str(ticket.priority),
                status=status,
                ticket_scope=(ticket.metadata or {}).get("ticket_scope"),
                title=ticket.title,
            )
        except Exception:
            pass

    def _graph_customer_id(self, ticket: Ticket) -> str:
        """The ticket's customer as the GRAPH keys it (CRN…), not the SQLite id (cust_…).

        upsert_ticket_node MATCHes on the graph id, so passing the SQLite one matches
        nothing and writes zero rows silently — the same id-namespace trap as Fix 63.
        """
        try:
            from services.neo4j_service.queries import get_customer_by_identifier
            for row in self.repository.list_customer_identifiers(ticket.customer_id) or []:
                found = get_customer_by_identifier(self.neo4j_client, row["identifier"])
                if found:
                    return found["customer_id"]
        except Exception:
            pass
        return ticket.customer_id

    def _ticket(self, ticket_id: str) -> Ticket:
        ticket = self.repository.get_ticket(ticket_id)
        if not ticket:
            raise KeyError(f"Ticket not found: {ticket_id}")
        return Ticket(**ticket)

    def _audit(self, ticket: Ticket, event_type: str, details: dict) -> None:
        self.repository.add_audit_event(
            event_type,
            new_id("corr"),
            customer_id=ticket.customer_id,
            conversation_id=ticket.conversation_id,
            ticket_id=ticket.ticket_id,
            details=details,
        )


def _scope_label(ticket_scope: str | None, intent: str) -> str:
    """Human-readable subtype for the referee prompt, derived from the scope tag.

    'transaction_dispute:card' -> 'card transaction dispute'. The scope subtype is
    the reliable discriminator between same-intent tickets (card vs upi), so it is
    surfaced prominently rather than left as a raw tag the model may ignore.
    """
    base = (intent or "ticket").replace("_", " ")
    if not ticket_scope or ":" not in ticket_scope:
        return base
    subtype = ticket_scope.split(":", 1)[1].replace("_", " ")
    if subtype in ("other", "manual review"):
        return base
    return f"{subtype} {base}"



def _case_messages(client, ticket_id: str) -> list[dict]:
    """Messages already linked to this ticket in the graph; [] if unavailable."""
    if client is None or not ticket_id:
        return []
    try:
        from services.neo4j_service.queries import get_case_messages
        return get_case_messages(client, ticket_id) or []
    except Exception:
        return []


def _load_transactions(customer_id: str | None) -> list[dict]:
    """This customer's transactions, or [] if the graph is unavailable."""
    if not customer_id:
        return []
    try:
        from services.neo4j_service.client import Neo4jClient
        from services.neo4j_service.queries import get_transactions
        return get_transactions(Neo4jClient(), customer_id, limit=50) or []
    except Exception:
        return []


def _referenced_txn(text: str, graph_context: dict | None) -> str | None:
    """The transaction this message is about, or None if it names none.

    The scope label is what decides "same matter or new one?", and it was derived
    purely from which payment-rail word the customer happened to type - upi, card,
    imps, neft, rtgs, atm. That measures VOCABULARY, not specificity, and the two come
    apart in both directions:

      "On 23 March I paid Rs.5,776.55 to Samarth Thaker"  -> no rail word -> ":other"
          the most specific message in the conversation, labelled vague, so the
          refinement path (which excludes ":other") skipped it and a duplicate ticket
          was opened.
      "I also have a problem with a UPI payment"          -> ":upi"
          names no transaction at all, but reads as specific and can therefore claim
          to be about a particular matter.

    The graph already knows which transactions this customer has. Matching against it
    answers a FACT - does this message name a record we hold - instead of guessing from
    a keyword. Measured on the seeded data: 10/10 correct, 0 false positives across all
    five customers, and no customer has two transactions sharing an amount or a payee,
    so a match is never ambiguous. The LLM referee this replaces answered the same case
    correctly 1 time in 5.

    Deliberately narrow: an amount must be >= 3 digits (so "5" cannot match), and only
    amount, payee name and txn id are considered.
    """
    if not text or not graph_context:
        return None
    # get_customer_context_for_customer does NOT include transactions - it loads loans,
    # claims, policies, cards, accounts, FDs and open_cases only. Verified against the
    # live payload rather than assumed: reading a "transactions" key here would have
    # returned None every time and the fix would have done nothing at all.
    transactions = graph_context.get("transactions")
    if transactions is None:
        transactions = _load_transactions(graph_context.get("customer_id"))
    if not transactions:
        return None
    lowered = text.lower().replace(",", "")
    for txn in transactions:
        txn_id = str(txn.get("txn_id") or "")
        if not txn_id:
            continue
        whole_amount = str(txn.get("amount") or "").split(".")[0]
        payee = str(txn.get("beneficiary_name") or "").lower()
        if txn_id.lower() in lowered:
            return txn_id
        if whole_amount and len(whole_amount) >= 3 and whole_amount in lowered:
            return txn_id
        if payee and payee in lowered:
            return txn_id
    return None


def _ticket_scope(intent: str, text: str, escalation_reason: str | None,
                  graph_context: dict | None = None) -> str | None:
    """Name the MATTER this message is about, so two messages on it can be matched.

    The scope answers "which incident is this?" - a phishing report and a disputed UPI
    charge are both fraud_report, and must not merge into one ticket.

    This used to begin `if not escalation_reason: return None`, which made sense while a
    ticket existed only when something escalated. Under Phase 4 every query gets a ticket,
    and most are NOT escalated - so that guard left the majority of tickets with a NULL
    scope. The consequences compound, because three things are gated on scope:

      * find_active_ticket_for_scope cannot match a scopeless ticket;
      * the refinement path (":other" -> specific) never runs;
      * the REFEREE never runs at all - it sits behind `if not existing and ticket_scope`.

    So a follow-up on the same matter would fork a new ticket every time, which is the
    exact failure the redesign exists to remove. Relatedness is a property of the text,
    not of whether a human was needed, so the scope is now computed for every message.
    `escalation_reason` is still accepted because some branches read it, and callers pass
    it unchanged.
    """
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))

    def has(*terms: str) -> bool:
        return any(term in lowered for term in terms)

    if intent == Intent.FRAUD_REPORT.value:
        if has("phishing", "phishing link", "entered my banking details", "shared otp", "shared my otp"):
            return "fraud_report:phishing_credential_compromise"
        if has("cannot access", "can't access", "locked out", "login blocked", "password changed"):
            return "fraud_report:account_access_compromise"
        if has("transferred money", "money transferred", "stole money", "money stolen", "funds stolen"):
            return "fraud_report:account_takeover_funds_stolen"
        if has("upi", "debit", "withdrawal", "transaction", "charge"):
            return "fraud_report:unauthorized_transaction"
        if tokens.intersection({"hack", "hacked", "fraud", "scam"}):
            return "fraud_report:account_takeover"
        return "fraud_report:other"

    if intent == Intent.TRANSACTION_DISPUTE.value:
        # A named transaction settles it: the customer is talking about THAT one, whichever
        # rail word they did or did not use. Checked before the keyword rails below, because
        # the rails answer the wrong question (see _referenced_txn).
        txn_id = _referenced_txn(text, graph_context)
        if txn_id:
            return f"transaction_dispute:txn:{txn_id}"
        # No transaction named, so this message does not identify a matter - whatever rail
        # word it contains. "I want to dispute a charge on my credit card" says card but
        # names no charge; treating it as the specific scope ":card" made it look like an
        # identified matter, so the later, genuinely specific message could not refine it
        # and forked instead. The rails below stay for the case they were built for: a
        # customer whose graph has no transaction records at all, where a rail word is the
        # only signal available.
        if graph_context and _load_transactions(graph_context.get("customer_id")):
            return "transaction_dispute:other"
        # Every payment rail the seeded Transaction records actually use. Previously only
        # upi/card were recognised, so an IMPS or NEFT dispute fell to ":other" — leaving
        # the ticket permanently "vague" and therefore eligible to absorb the next
        # unrelated specific message via the refinement rule above.
        if has("upi"):
            return "transaction_dispute:upi"
        if has("card", "credit card", "debit card"):
            return "transaction_dispute:card"
        if has("imps"):
            return "transaction_dispute:imps"
        if has("neft"):
            return "transaction_dispute:neft"
        if has("rtgs"):
            return "transaction_dispute:rtgs"
        if has("atm"):
            return "transaction_dispute:atm"
        if has("netbanking", "net banking", "internet banking"):
            return "transaction_dispute:netbanking"
        if has("pos ", "pos purchase", "point of sale", "swipe"):
            return "transaction_dispute:pos"
        return "transaction_dispute:other"

    if intent == Intent.LOAN_DEFAULT_NOTICE.value:
        return "loan_default_notice:paid_emi_dispute" if has("paid", "already paid") else "loan_default_notice:default"

    if intent == Intent.CARD_MANAGEMENT.value:
        if has("lost", "stolen"):
            return "card_management:lost_or_stolen"
        if has("block", "blocked"):
            return "card_management:block_or_unblock"
        return "card_management:other"

    if intent in {Intent.INSURANCE_CLAIM.value, Intent.CLAIM_STATUS.value}:
        if has("hospital", "hospitalisation", "hospitalization", "medical"):
            return f"{intent}:health_claim"
        if has("accident"):
            return f"{intent}:accident_claim"
        return f"{intent}:other"

    if intent == Intent.KYC_UPDATE.value:
        if has("aadhaar", "aadhar"):
            return "kyc_update:aadhaar"
        if has("pan"):
            return "kyc_update:pan"
        if has("address"):
            return "kyc_update:address"
        return "kyc_update:other"

    return f"{intent}:manual_review"
