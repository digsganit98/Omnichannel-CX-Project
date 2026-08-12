import re

from shared.schemas.intents import Intent, IntentResult, Urgency

from .sentiment import detect_sentiment
from .urgency import detect_urgency


KEYWORDS = {
    Intent.HUMAN_ESCALATION:        {"human", "agent", "representative", "speak to someone", "call me"},
    Intent.COMPLAINT:               {"complaint", "terrible", "unacceptable", "angry", "frustrated", "worst service"},
    Intent.FRAUD_REPORT:            {"fraud", "hack", "phishing", "scam", "money stolen", "account hacked", "unauthorized transaction"},
    Intent.TRANSACTION_DISPUTE:     {"dispute", "wrong debit", "incorrect charge", "charge error", "not authorized", "unknown transaction"},
    Intent.FUND_TRANSFER:           {"transfer", "neft", "rtgs", "imps", "send money", "wire transfer", "beneficiary"},
    # Fixed deposits live here, not on a separate intent: neo4j_answer's
    # account_balance_inquiry branch already fetches BOTH accounts and fixed deposits
    # (principal, rate, tenure, maturity date/amount), so FD questions only need to reach
    # this intent to be answered from the graph.
    Intent.ACCOUNT_BALANCE_INQUIRY: {"balance", "account balance", "available funds", "how much in my account", "check balance",
                                     "fixed deposit", "fd maturity", "my fd", "fd account", "deposit maturity", "maturity date",
                                     "maturity amount"},
    Intent.GENERAL_INQUIRY:         {"sip", "systematic investment plan", "elss", "equity linked savings scheme",
                                     "mutual fund", "tax saving", "tax benefits", "investment plan"},
    Intent.LOAN_STATUS:             {"loan balance", "emi", "repayment", "outstanding loan", "loan status", "loan due", "emi due"},
    Intent.LOAN_APPLICATION:        {"apply loan", "new loan", "personal loan", "home loan", "loan eligibility", "loan apply"},
    Intent.LOAN_DEFAULT_NOTICE:     {"default", "overdue", "missed emi", "npa", "loan overdue", "pending emi"},
    Intent.POLICY_STATUS:           {"policy", "insurance policy", "premium", "policy number", "coverage", "policy status"},
    Intent.CLAIM_STATUS:            {"claim status", "status of my claim", "track my claim", "claim update",
                                     "existing claim", "claim progress"},
    Intent.INSURANCE_CLAIM:         {"claim", "file claim", "submit claim", "make a claim", "accident",
                                     "damage claim", "reimbursement", "hospitalization"},
    Intent.CARD_MANAGEMENT:         {"block card", "lost card", "stolen card", "card limit", "pin change", "debit card", "credit card", "card blocked"},
    Intent.KYC_UPDATE:              {"kyc", "update documents", "pan card", "aadhaar", "address proof", "kyc update", "document update"},
    Intent.TICKET_STATUS:           {"ticket status", "case status", "query status", "reference number",
                                     "status of my", "update on my", "what happened to my",
                                     "my complaint status", "follow up", "ticket number",
                                     "is my request", "any update", "complaint reference",
                                     "pending status", "pending ticket", "any pending",
                                     "anything pending", "pending tickets"},
}


def _matches(keyword: str, lowered: str) -> bool:
    """Whole-word keyword match.

    A plain `keyword in text` test matches inside longer words: "emi" hides in
    "pr-emi-um", so every insurance premium question scored for BOTH loan_status
    (via "emi") and policy_status (via "premium") — and the tie broke toward the
    intent declared first, routing insurance questions to Loans. "sip" hides in
    "gossip" the same way. Multi-word keywords ("loan due") keep substring
    behaviour; the boundary only guards the ends of the phrase.

    A trailing inflection is still a match, because a bare word boundary would
    otherwise LOSE matches the substring test used to get — customers write
    "what are my claims?", "my account was hacked", "someone is hacking my card".
    So plural (-s/-es/-ies) and verb (-ed/-ing/-d) endings are allowed after the
    keyword, while a hit *inside* a longer word is still rejected.
    """
    return re.search(
        rf"(?<!\w){re.escape(keyword)}(?:e?s|ies|e?d|ing)?(?!\w)", lowered
    ) is not None


def classify_intent(text: str) -> IntentResult:
    lowered = text.lower()
    intent_override = _process_or_status_intent(lowered)
    scores = {
        intent: sum(1 for keyword in keywords if _matches(keyword, lowered))
        for intent, keywords in KEYWORDS.items()
    }
    intent, score = max(scores.items(), key=lambda item: item[1])
    if intent_override is not None:
        intent = intent_override
        score = max(score, 1)
    elif score == 0:
        intent = Intent.GENERAL_INQUIRY
    sentiment = detect_sentiment(text)
    urgency = Urgency(detect_urgency(text, sentiment))
    confidence = min(0.95, 0.55 + score * 0.12) if score else 0.45
    return IntentResult(
        intent=intent,
        confidence=confidence,
        urgency=urgency,
        sentiment=sentiment,
        reason="Matched BFSI intent rules." if score else "No specific intent keyword matched.",
        analysis_source="rule_fallback",
    )


def _process_or_status_intent(lowered: str) -> Intent | None:
    """Resolve process-vs-account-status phrases before broad keyword scoring.

    Uses the same whole-word matching as the keyword scorer above, so a term like
    "default" fires on "default"/"default notice" but not inside "defaulted", and
    "claim" does not fire inside "claimant".
    """
    def has(*terms: str) -> bool:
        return any(_matches(term, lowered) for term in terms)

    if has("human", "agent", "representative", "speak to someone", "connect me"):
        return Intent.HUMAN_ESCALATION

    if has("default", "overdue", "missed emi", "npa", "loan overdue", "default notice"):
        return Intent.LOAN_DEFAULT_NOTICE

    status_terms = ("status", "track", "progress", "update on", "what happened")
    process_terms = ("how do i", "how can i", "steps", "process", "apply", "file", "submit")

    if has("claim"):
        if has(*status_terms):
            return Intent.CLAIM_STATUS
        if has(*process_terms):
            return Intent.INSURANCE_CLAIM

    if has("loan"):
        if has(*status_terms) or has("already applied"):
            return Intent.LOAN_STATUS
        if has(*process_terms):
            return Intent.LOAN_APPLICATION

    return None
