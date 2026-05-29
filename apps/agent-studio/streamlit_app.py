import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.channel_service.adapters.email_adapter import EmailAdapter
from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
from services.orchestration_service.router import OmnichannelRouter
from shared.schemas.messages import EmailWebhookPayload, WhatsAppWebhookPayload
from shared.utils.in_memory_store import store

st.set_page_config(page_title="Agent Studio", layout="wide")
st.title("Agent Studio")

channel = st.segmented_control("Channel", ["WhatsApp", "Email"], default="WhatsApp")
customer = st.text_input("Customer", value="customer@example.com" if channel == "Email" else "919999999999")
message = st.text_area("Message", value="Where is my order?")

if st.button("Resolve Query", type="primary"):
    router = OmnichannelRouter()
    if channel == "WhatsApp":
        inbound = WhatsAppAdapter().normalize(
            WhatsAppWebhookPayload(from_=customer, text=message, profile_name="Demo Customer")
        )
    else:
        inbound = EmailAdapter().normalize(
            EmailWebhookPayload(from_email=customer, subject="Customer query", body=message)
        )
    result = router.handle(inbound)
    st.subheader("Suggested Response")
    st.write(result.message)
    st.json(result.model_dump())

st.subheader("Open Tickets")
st.dataframe([ticket.model_dump() for ticket in store.tickets.values()], use_container_width=True)
