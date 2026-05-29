import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.utils.in_memory_store import store
from services.analytics_service.consolidated_records import (
    load_consolidated_records,
    load_uploaded_records,
    summarize_consolidated_records,
)

st.set_page_config(page_title="CX Analytics", layout="wide")
st.title("CX Analytics")

metrics = store.metrics or {"email_messages": 0, "whatsapp_messages": 0, "resolved": 0, "tickets_created": 0}
cols = st.columns(len(metrics))
for col, (name, value) in zip(cols, metrics.items()):
    col.metric(name.replace("_", " ").title(), value)

df = pd.DataFrame([{"metric": key, "value": value} for key, value in metrics.items()])
if not df.empty:
    st.plotly_chart(px.bar(df, x="metric", y="value"), use_container_width=True)

records = load_consolidated_records()
uploaded_records = load_uploaded_records()
if records:
    st.subheader("Synthetic Omnichannel Records")
    summary = summarize_consolidated_records(records)
    cols = st.columns(3)
    cols[0].metric("Synthetic Records", summary["total_records"])
    cols[1].metric("Auto Resolved", summary["auto_resolved"])
    cols[2].metric("Tickets Created", summary["tickets_created"])

    flat_records = []
    for record in records:
        flat_records.append(
            {
                "channel": record["source"]["channel"],
                "customer": record["customer"]["name"],
                "intent": record["classification"]["intent"],
                "sentiment": record["classification"]["sentiment"],
                "urgency": record["classification"]["urgency"],
                "status": record["resolution"]["status"],
                "ticket": record["ticket"]["ticket_id"] if record["ticket"] else None,
            }
        )
    st.dataframe(flat_records, use_container_width=True)

    channel_df = pd.DataFrame(
        [{"channel": key, "count": value} for key, value in summary["channels"].items()]
    )
    intent_df = pd.DataFrame(
        [{"intent": key, "count": value} for key, value in summary["intents"].items()]
    )
    chart_cols = st.columns(2)
    chart_cols[0].plotly_chart(px.pie(channel_df, names="channel", values="count"), use_container_width=True)
    chart_cols[1].plotly_chart(px.bar(intent_df, x="intent", y="count"), use_container_width=True)

if uploaded_records:
    st.subheader("Uploaded Workbook Records")
    uploaded_summary = summarize_consolidated_records(uploaded_records)
    cols = st.columns(3)
    cols[0].metric("Workbook Records", uploaded_summary["total_records"])
    cols[1].metric("Workbook Auto Resolved", uploaded_summary["auto_resolved"])
    cols[2].metric("Workbook Tickets", uploaded_summary["tickets_created"])
    st.dataframe(
        [
            {
                "Customer_ID": record["Customer"]["Customer_ID"],
                "Name": record["Customer"]["Name"],
                "Channel": record["Ticket"]["Channel"],
                "Issue_Type": record["Ticket"]["Issue_Type"],
                "Sentiment": record["Ticket"]["Sentiment"],
                "Resolution_Status": record["Ticket"]["Resolution_Status"],
                "Intent": record["AI_Enrichment"]["Intent"],
                "Ticket_Action": record["AI_Enrichment"]["Ticket_Action"],
            }
            for record in uploaded_records[:100]
        ],
        use_container_width=True,
    )
