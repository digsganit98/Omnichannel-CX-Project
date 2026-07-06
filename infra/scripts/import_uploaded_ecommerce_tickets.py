import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.scripts.consolidate_synthetic_tickets import (
    INTENT_TO_TEAM,
    classify_intent,
    detect_urgency,
    extract_topic,
    next_best_action,
    search_knowledge_base,
)


INPUT_PATH = ROOT / "data" / "uploaded_docs" / "ecommerce_tickets_synthetic (1).xlsx"
OUTPUT_PATH = ROOT / "data" / "exports" / "uploaded_ecommerce_omnichannel_records.json"

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_sheet_rows(workbook: zipfile.ZipFile, sheet_name: str) -> list[dict]:
    sheet_map = {
        "Customers": "xl/worksheets/sheet1.xml",
        "Accounts": "xl/worksheets/sheet2.xml",
        "Tickets": "xl/worksheets/sheet3.xml",
    }
    root = ET.fromstring(workbook.read(sheet_map[sheet_name]))
    rows = []
    for row in root.findall(".//a:row", NS):
        rows.append([cell_value(cell) for cell in row.findall("a:c", NS)])
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(row)]


def cell_value(cell: ET.Element) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//a:t", NS))
    value = cell.find("a:v", NS)
    return "" if value is None else value.text or ""


def excel_serial_to_iso(value: str) -> str:
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat()
    # Excel's Windows date system starts at 1899-12-30 for serial conversion.
    dt = datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=serial)
    return dt.isoformat()


def build_excel_aligned_record(
    ticket: dict,
    customers: dict[str, dict],
    accounts: dict[str, dict],
    seen_customers: dict[str, list[str]],
) -> dict:
    customer = customers.get(ticket["Customer_ID"], {})
    account = accounts.get(ticket["Customer_ID"], {})
    channel = normalize_channel(ticket["Channel"])
    message = ticket["Message"]
    subject = ticket["Issue_Type"]
    normalized_text = f"{subject}\n\n{message}".strip() if channel == "email" else message.strip()
    intent = classify_intent(normalized_text)
    sentiment = (ticket.get("Sentiment") or "Neutral").lower()
    urgency = detect_urgency(normalized_text, sentiment)
    topic = extract_topic(normalized_text)
    answer, confidence, source = search_knowledge_base(normalized_text, intent)
    source_status = (ticket.get("Resolution_Status") or "").lower()
    should_ticket = confidence < 0.25 or urgency == "high" or source_status in {"open", "escalated"}
    ticket_action = "ticket_created" if should_ticket else "auto_resolved"
    assigned_team = INTENT_TO_TEAM.get(intent, "customer_support") if should_ticket else None
    priority = "high" if urgency == "high" else "medium" if should_ticket else None
    customer_id = ticket["Customer_ID"]
    previous_channels = seen_customers.setdefault(customer_id, [])
    is_cross_channel = channel not in previous_channels and bool(previous_channels)
    if channel not in previous_channels:
        previous_channels.append(channel)

    return {
        "Customer": {
            "Customer_ID": customer_id,
            "Name": customer.get("Name") or customer_id,
            "City": customer.get("City"),
            "Email": customer.get("Email"),
            "Phone": customer.get("Phone"),
            "Segment": customer.get("Segment"),
            "Language": customer.get("Language"),
        },
        "Account": {
            "Account_ID": account.get("Account_ID"),
            "Customer_ID": customer_id,
            "Account_Type": account.get("Account_Type"),
            "Total_Spent": float(account["Total_Spent"]) if account.get("Total_Spent") else None,
            "Status": account.get("Status"),
            "Join_Date": excel_serial_to_iso(account.get("Join_Date", "")) if account.get("Join_Date") else None,
        },
        "Ticket": {
            "Ticket_ID": ticket["Ticket_ID"],
            "Customer_ID": customer_id,
            "Channel": ticket.get("Channel"),
            "Issue_Type": subject,
            "Sentiment": ticket.get("Sentiment"),
            "Message": message,
            "Order_ID": ticket.get("Order_ID"),
            "Resolution_Status": ticket.get("Resolution_Status"),
            "Timestamp": excel_serial_to_iso(ticket.get("Timestamp", "")),
        },
        "AI_Enrichment": {
            "Normalized_Channel": channel,
            "Normalized_Text": normalized_text,
            "Intent": intent,
            "Detected_Sentiment": sentiment,
            "Urgency": urgency,
            "Topic": topic,
            "Retrieval_Confidence": confidence,
            "Knowledge_Source": source,
            "Generated_Response": answer or "I have captured the details and will route this to the right support team.",
            "Ticket_Action": ticket_action,
            "Assigned_Team": assigned_team,
            "Priority": priority,
            "Next_Best_Action": next_best_action(intent, sentiment, urgency, should_ticket),
            "Conversation_ID": f"conv_{customer_id}",
            "Is_Cross_Channel": is_cross_channel,
            "Previous_Channels": previous_channels.copy(),
            "Processed_At": datetime.now(timezone.utc).isoformat(),
        },
    }


def normalize_channel(channel: str) -> str:
    lowered = channel.strip().lower()
    if lowered == "email":
        return "email"
    if lowered == "whatsapp":
        return "whatsapp"
    return "webchat"


def issue_to_category(issue_type: str) -> str:
    lowered = issue_type.lower()
    if "refund" in lowered or "wrong product" in lowered:
        return "returns"
    if "payment" in lowered:
        return "payments"
    if "delivery" in lowered:
        return "fulfillment"
    return "general"


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing uploaded workbook: {INPUT_PATH}")

    with zipfile.ZipFile(INPUT_PATH) as workbook:
        customers = {
            row["Customer_ID"]: row
            for row in read_sheet_rows(workbook, "Customers")
        }
        accounts = {
            row["Customer_ID"]: row
            for row in read_sheet_rows(workbook, "Accounts")
        }
        tickets = read_sheet_rows(workbook, "Tickets")

    seen_customers: dict[str, list[str]] = {}
    consolidated = [
        build_excel_aligned_record(ticket, customers, accounts, seen_customers)
        for ticket in tickets
        if normalize_channel(ticket.get("Channel", "")) in {"email", "whatsapp"}
    ]
    OUTPUT_PATH.write_text(json.dumps(consolidated, indent=2), encoding="utf-8")

    print(f"source_tickets={len(tickets)}")
    print(f"email_whatsapp_records={len(consolidated)}")
    print(f"output={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
