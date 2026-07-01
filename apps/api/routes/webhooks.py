from apps.api.dependencies.runtime import get_router
from services.channel_service.adapters.email_adapter import EmailAdapter
from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
from shared.schemas.messages import EmailWebhookPayload, WhatsAppWebhookPayload
from shared.schemas.responses import ChannelResponse


def handle_whatsapp_message(payload: WhatsAppWebhookPayload) -> ChannelResponse:
    return get_router().handle(WhatsAppAdapter().normalize(payload))


def handle_email_message(payload: EmailWebhookPayload) -> ChannelResponse:
    return get_router().handle(EmailAdapter().normalize(payload))
