from shared.schemas.messages import Channel, InboundMessage, WhatsAppWebhookPayload

from .base import ChannelAdapter


class WhatsAppAdapter(ChannelAdapter):
    def normalize(self, payload: WhatsAppWebhookPayload) -> InboundMessage:
        return InboundMessage(
            channel=Channel.WHATSAPP,
            customer_id=f"wa:{payload.from_}",
            display_name=payload.profile_name,
            text=payload.text,
            external_message_id=payload.message_id,
            metadata=payload.metadata,
        )
