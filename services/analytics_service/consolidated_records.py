import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDS_PATH = ROOT / "data" / "exports" / "consolidated_omnichannel_records.json"
UPLOADED_RECORDS_PATH = ROOT / "data" / "exports" / "uploaded_ecommerce_omnichannel_records.json"


def load_consolidated_records(path: Path = DEFAULT_RECORDS_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_uploaded_records() -> list[dict]:
    return load_consolidated_records(UPLOADED_RECORDS_PATH)


def summarize_consolidated_records(records: list[dict]) -> dict:
    summary = {
        "total_records": len(records),
        "auto_resolved": 0,
        "tickets_created": 0,
        "channels": {},
        "intents": {},
        "sentiments": {},
    }
    for record in records:
        channel = record.get("source", {}).get("channel") or record.get("AI_Enrichment", {}).get("Normalized_Channel")
        intent = record.get("classification", {}).get("intent") or record.get("AI_Enrichment", {}).get("Intent")
        sentiment = (
            record.get("classification", {}).get("sentiment")
            or record.get("AI_Enrichment", {}).get("Detected_Sentiment")
        )
        status = record.get("resolution", {}).get("status") or record.get("AI_Enrichment", {}).get("Ticket_Action")
        summary["channels"][channel] = summary["channels"].get(channel, 0) + 1
        summary["intents"][intent] = summary["intents"].get(intent, 0) + 1
        summary["sentiments"][sentiment] = summary["sentiments"].get(sentiment, 0) + 1
        if status == "auto_resolved":
            summary["auto_resolved"] += 1
        elif status == "ticket_created":
            summary["tickets_created"] += 1
    return summary
