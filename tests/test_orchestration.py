from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
from services.orchestration_service.router import OmnichannelRouter
from shared.schemas.messages import WhatsAppWebhookPayload


def test_whatsapp_order_query_resolves_from_knowledge_base():
    payload = WhatsAppWebhookPayload(from_="919999999999", text="Where is my order delivery?")
    message = WhatsAppAdapter().normalize(payload)
    response = OmnichannelRouter().handle(message)

    assert response.resolved is True
    assert response.intent == "order_tracking"
    assert response.ticket_id is None
