import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = ROOT / "data" / "synthetic" / "ecommerce_channel_messages.json"
OUTPUT_PATH = ROOT / "data" / "exports" / "consolidated_omnichannel_records.json"

INTENT_KEYWORDS = {
    "refund_request": {"refund", "return", "cancel", "money back", "damaged"},
    "billing_issue": {"invoice", "bill", "charged", "payment", "paid", "tax invoice", "payment issue"},
    "technical_support": {"error", "not working", "failed", "bug", "login", "password"},
    "order_tracking": {"order", "track", "delivery", "shipment", "where is", "arrive"},
}

INTENT_TO_TEAM = {
    "order_tracking": "fulfillment",
    "refund_request": "returns_and_refunds",
    "billing_issue": "billing",
    "technical_support": "technical_support",
    "general_question": "customer_support",
}

NEGATIVE = {
    "angry",
    "bad",
    "terrible",
    "frustrated",
    "late",
    "failed",
    "problem",
    "damaged",
    "not received",
    "not credited",
    "charged twice",
}
POSITIVE = {"thanks", "great", "good", "helpful", "resolved"}
URGENT = {"urgent", "asap", "immediately", "critical", "escalate", "complaint"}


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
    if any(word in lowered for word in NEGATIVE):
        return "negative"
    if any(word in lowered for word in POSITIVE):
        return "positive"
    return "neutral"


def detect_urgency(text: str, sentiment: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in URGENT):
        return "high"
    if sentiment == "negative":
        return "medium"
    return "low"


def extract_topic(text: str) -> str:
    tokens = [token.strip(".,!?").lower() for token in text.split()]
    meaningful = [token for token in tokens if len(token) > 4]
    return meaningful[0] if meaningful else "general"


def search_knowledge_base(text: str, intent: str | None = None) -> tuple[str | None, float, str | None]:
    query_terms = {term.strip(".,!?").lower() for term in text.split() if len(term) > 2}
    best_score = 0.0
    best_source = None
    best_answer = None
    preferred_sources = {
        "order_tracking": "orders.md",
        "refund_request": "refunds.md",
        "billing_issue": "billing.md",
    }
    preferred_source = preferred_sources.get(intent or "")

    for doc in (ROOT / "data" / "knowledge_base").glob("*.md"):
        content = doc.read_text(encoding="utf-8")
        lowered = content.lower()
        overlap = sum(1 for term in query_terms if term in lowered)
        score = overlap / max(len(query_terms), 1)
        if preferred_source == doc.name and score > 0:
            score += 0.35
        if score > best_score:
            best_score = score
            best_source = doc.name
            best_answer = next(
                (
                    part.strip()
                    for part in content.split("\n\n")
                    if not part.strip().startswith("#") and any(term in part.lower() for term in query_terms)
                ),
                None,
            )

    return best_answer, round(min(best_score, 1.0), 2), best_source


def extract_entities(raw: dict, normalized_text: str) -> dict:
    order = raw.get("order") or {}
    order_id = order.get("order_id")
    if not order_id:
        match = re.search(r"\bOD\d+\b", normalized_text, flags=re.IGNORECASE)
        order_id = match.group(0).upper() if match else None

    return {
        "order_id": order_id,
        "return_id": order.get("return_id"),
        "payment_id": order.get("payment_id"),
        "invoice_id": order.get("invoice_id"),
        "category": order.get("category"),
        "order_value": order.get("order_value"),
    }


def normalize_channel_message(raw: dict) -> tuple[str | None, str, str]:
    channel = raw["channel"]
    payload = raw["payload"]
    if channel == "email":
        subject = payload["subject"]
        body = payload["body"]
        normalized_text = f"{subject}\n\n{body}".strip()
    elif channel == "whatsapp":
        subject = None
        body = payload["text"]
        normalized_text = body.strip()
    else:
        raise ValueError(f"Unsupported channel: {channel}")
    return subject, body, normalized_text


def build_ticket(intent: str, urgency: str, subject: str | None, text: str) -> dict:
    priority = "high" if urgency == "high" else "medium"
    return {
        "ticket_id": f"tkt_{uuid4().hex[:12]}",
        "title": subject or f"{intent.replace('_', ' ').title()} request",
        "priority": priority,
        "assigned_team": INTENT_TO_TEAM.get(intent, "customer_support"),
        "status": "open",
        "summary": text[:180],
    }


def next_best_action(intent: str, sentiment: str, urgency: str, has_ticket: bool) -> str:
    if has_ticket:
        return "Review customer context, validate order details, and update the ticket with the next action."
    if intent == "refund_request":
        return "Validate return eligibility and share refund processing timelines."
    if sentiment == "negative" or urgency != "low":
        return "Use an empathetic response and monitor for escalation."
    return "Share the answer and confirm whether the customer needs anything else."


def coaching_tip(sentiment: str) -> str:
    if sentiment == "negative":
        return "Acknowledge the customer impact before explaining the process."
    return "Keep the reply concise and specific to the customer's order."


def suggested_reply(status: str, answer: str, ticket: dict | None) -> str:
    if ticket:
        return (
            f"I have created ticket {ticket['ticket_id']} and routed it to our "
            f"{ticket['assigned_team'].replace('_', ' ')} team. We will update you shortly."
        )
    return answer


def consolidate_record(raw: dict, seen_customers: dict[str, list[str]]) -> dict:
    subject, body, normalized_text = normalize_channel_message(raw)
    intent = classify_intent(normalized_text)
    sentiment = detect_sentiment(normalized_text)
    source_sentiment = (raw.get("order") or {}).get("source_sentiment")
    if source_sentiment:
        sentiment = source_sentiment.lower()
    urgency = detect_urgency(normalized_text, sentiment)
    topic = extract_topic(normalized_text)
    answer, confidence, source = search_knowledge_base(normalized_text, intent)
    source_status = ((raw.get("order") or {}).get("source_resolution_status") or "").lower()
    should_ticket = confidence < 0.25 or urgency == "high" or source_status in {"open", "escalated"}
    ticket = build_ticket(intent, urgency, subject, normalized_text) if should_ticket else None
    status = "ticket_created" if ticket else "auto_resolved"
    fallback_answer = "I have captured the details and will route this to the right support team."
    final_answer = answer or fallback_answer
    customer_id = raw["customer"]["customer_id"]
    previous_channels = seen_customers.setdefault(customer_id, [])
    is_cross_channel = raw["channel"] not in previous_channels and bool(previous_channels)
    if raw["channel"] not in previous_channels:
        previous_channels.append(raw["channel"])

    return {
        "record_id": f"cx_{uuid4().hex[:12]}",
        "source": {
            "channel": raw["channel"],
            "external_message_id": raw["message_id"],
            "received_at": raw["created_at"],
        },
        "customer": {
            "customer_id": customer_id,
            "name": raw["customer"]["name"],
            "segment": raw["customer"]["segment"],
            "contact": {
                "phone": raw["customer"].get("phone"),
                "email": raw["customer"].get("email"),
            },
        },
        "conversation": {
            "conversation_id": f"conv_{customer_id}",
            "is_cross_channel": is_cross_channel,
            "previous_channels": previous_channels.copy(),
        },
        "message": {
            "subject": subject,
            "body": body,
            "normalized_text": normalized_text,
            "entities": extract_entities(raw, normalized_text),
        },
        "classification": {
            "intent": intent,
            "sentiment": sentiment,
            "urgency": urgency,
            "topic": topic,
            "confidence": confidence,
        },
        "resolution": {
            "status": status,
            "answer": final_answer,
            "knowledge_source": source,
        },
        "ticket": ticket,
        "agent_assist": {
            "next_best_action": next_best_action(intent, sentiment, urgency, ticket is not None),
            "coaching_tip": coaching_tip(sentiment),
            "suggested_reply": suggested_reply(status, final_answer, ticket),
        },
        "audit": {
            "processed_by": "synthetic_consolidator_v1",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def main() -> None:
    raw_records = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    seen_customers: dict[str, list[str]] = {}
    consolidated = [consolidate_record(raw, seen_customers) for raw in raw_records]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(consolidated, indent=2), encoding="utf-8")

    print(f"records={len(consolidated)}")
    print(f"output={OUTPUT_PATH}")
    for record in consolidated:
        ticket_id = record["ticket"]["ticket_id"] if record["ticket"] else None
        print(
            f"{record['source']['channel']} "
            f"{record['classification']['intent']} "
            f"{record['classification']['sentiment']} "
            f"{record['resolution']['status']} "
            f"ticket={ticket_id}"
        )


if __name__ == "__main__":
    main()
