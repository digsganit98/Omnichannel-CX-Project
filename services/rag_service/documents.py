import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


ROOT = Path(__file__).resolve().parents[2]


def load_knowledge_documents() -> list[Document]:
    documents: list[Document] = []
    documents.extend(_load_markdown_kb())
    documents.extend(_load_uploaded_ticket_records())
    return _split_documents(documents)


def _load_markdown_kb() -> list[Document]:
    docs = []
    for path in (ROOT / "data" / "knowledge_base").glob("*.md"):
        docs.append(
            Document(
                page_content=path.read_text(encoding="utf-8"),
                metadata={
                    "source": path.name,
                    "doc_type": "knowledge_base",
                    "document_version": str(int(path.stat().st_mtime)),
                },
            )
        )
    return docs


def _load_uploaded_ticket_records(limit: int = 250) -> list[Document]:
    path = ROOT / "data" / "exports" / "uploaded_ecommerce_omnichannel_records.json"
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))[:limit]
    docs = []
    for record in records:
        customer = record.get("Customer", {})
        account = record.get("Account", {})
        ticket = record.get("Ticket", {})
        enrichment = record.get("AI_Enrichment", {})
        text = "\n".join(
            [
                f"Customer: {customer.get('Name')} ({customer.get('Customer_ID')})",
                f"Segment: {customer.get('Segment')} | City: {customer.get('City')}",
                f"Account type: {account.get('Account_Type')} | Status: {account.get('Status')}",
                f"Ticket: {ticket.get('Ticket_ID')} | Channel: {ticket.get('Channel')}",
                f"Issue type: {ticket.get('Issue_Type')} | Sentiment: {ticket.get('Sentiment')}",
                f"Message: {ticket.get('Message')}",
                f"Order ID: {ticket.get('Order_ID')} | Resolution status: {ticket.get('Resolution_Status')}",
                f"Intent: {enrichment.get('Intent')} | Generated response: {enrichment.get('Generated_Response')}",
            ]
        )
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source": "uploaded_ecommerce_omnichannel_records.json",
                    "doc_type": "ticket_history",
                    "ticket_id": ticket.get("Ticket_ID"),
                    "customer_id": customer.get("Customer_ID"),
                    "channel": ticket.get("Channel"),
                    "issue_type": ticket.get("Issue_Type"),
                },
            )
        )
    return docs


def _split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    return splitter.split_documents(documents)
