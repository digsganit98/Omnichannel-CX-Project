from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


INTENT_KEYWORDS = {
    "refund_request": {"refund", "return", "cancel", "money back"},
    "billing_issue": {"invoice", "bill", "charged", "payment", "paid", "payment issue"},
    "technical_support": {"error", "not working", "failed", "bug", "login", "password"},
    "order_tracking": {"order", "track", "delivery", "shipment", "where is"},
}

INTENT_TO_TEAM = {
    "order_tracking": "fulfillment",
    "refund_request": "billing",
    "billing_issue": "billing",
    "technical_support": "technical_support",
    "general_question": "customer_support",
}

NEGATIVE = {"angry", "bad", "terrible", "frustrated", "late", "failed", "problem", "damaged"}
URGENT = {"urgent", "asap", "immediately", "critical", "escalate", "complaint"}


@dataclass
class SimulatedMessage:
    channel: str
    customer_id: str
    text: str
    subject: str | None = None


def classify_intent(text: str) -> str:
    lowered = text.lower()
    scores = {
        intent: sum(1 for keyword in keywords if keyword in lowered)
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    priority = {"refund_request": 4, "billing_issue": 3, "technical_support": 2, "order_tracking": 1}
    best_intent, best_score = max(scores.items(), key=lambda item: (item[1], priority.get(item[0], 0)))
    return best_intent if best_score > 0 else "general_question"


def detect_sentiment(text: str) -> str:
    lowered = text.lower()
    return "negative" if any(word in lowered for word in NEGATIVE) else "neutral"


def detect_urgency(text: str, sentiment: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in URGENT):
        return "high"
    return "medium" if sentiment == "negative" else "low"


def search_knowledge_base(text: str) -> tuple[str | None, float, str | None]:
    kb_dir = Path(__file__).resolve().parents[2] / "data" / "knowledge_base"
    query_terms = {term.strip(".,!?").lower() for term in text.split() if len(term) > 2}
    best_score = 0.0
    best_source = None
    best_answer = None

    for doc in kb_dir.glob("*.md"):
        content = doc.read_text(encoding="utf-8")
        lowered = content.lower()
        overlap = sum(1 for term in query_terms if term in lowered)
        score = overlap / max(len(query_terms), 1)
        if score > best_score:
            best_score = score
            best_source = doc.name
            best_answer = next(
                (
                    part.strip()
                    for part in content.split("\n\n")
                    if not part.strip().startswith("#") and any(term in part.lower() for term in query_terms)
                ),
                content.strip(),
            )

    return best_answer, round(best_score, 2), best_source


def handle_message(message: SimulatedMessage) -> dict:
    intent = classify_intent(message.text)
    sentiment = detect_sentiment(message.text)
    urgency = detect_urgency(message.text, sentiment)
    answer, confidence, source = search_knowledge_base(message.text)
    should_ticket = confidence < 0.25 or urgency == "high"
    ticket_id = f"tkt_{uuid4().hex[:12]}" if should_ticket else None

    if should_ticket:
        response = (
            "I have captured your request and created a support ticket. "
            f"Our {INTENT_TO_TEAM.get(intent, 'customer_support').replace('_', ' ')} team will review it."
        )
    else:
        response = answer

    return {
        "channel": message.channel,
        "customer_id": message.customer_id,
        "intent": intent,
        "sentiment": sentiment,
        "urgency": urgency,
        "confidence": confidence,
        "resolved": not should_ticket,
        "ticket_id": ticket_id,
        "source": source,
        "response": response,
    }


def main() -> None:
    scenarios = [
        SimulatedMessage(
            channel="whatsapp",
            customer_id="wa:919999999999",
            text="Where is my order delivery?",
        ),
        SimulatedMessage(
            channel="email",
            customer_id="email:customer@example.com",
            subject="Refund issue",
            text="Refund issue\n\nI want a refund for my last order.",
        ),
        SimulatedMessage(
            channel="whatsapp",
            customer_id="wa:918888888888",
            text="Urgent complaint. My login has failed and I need help immediately.",
        ),
    ]

    for index, scenario in enumerate(scenarios, start=1):
        result = handle_message(scenario)
        print(f"\nScenario {index}: {result['channel']} from {result['customer_id']}")
        print(f"intent={result['intent']} sentiment={result['sentiment']} urgency={result['urgency']}")
        print(f"resolved={result['resolved']} confidence={result['confidence']} ticket_id={result['ticket_id']}")
        print(f"source={result['source']}")
        print(f"response={result['response']}")


if __name__ == "__main__":
    main()
