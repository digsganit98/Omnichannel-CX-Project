from services.channel_service.adapters.email_adapter import EmailAdapter
from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
from services.orchestration_service.router import OmnichannelRouter
from shared.schemas.messages import EmailWebhookPayload, WhatsAppWebhookPayload
from shared.schemas.responses import ChannelResponse

router = OmnichannelRouter()


def handle_whatsapp_message(payload: WhatsAppWebhookPayload) -> ChannelResponse:
    message = WhatsAppAdapter().normalize(payload)
    return router.handle(message)


def handle_email_message(payload: EmailWebhookPayload) -> ChannelResponse:
    message = EmailAdapter().normalize(payload)
    return router.handle(message)
