from shared.schemas.messages import Channel, InboundMessage, WhatsAppWebhookPayload
from shared.utils.ids import new_id

from .base import ChannelAdapter


class WhatsAppAdapter(ChannelAdapter):
    def normalize(self, payload: WhatsAppWebhookPayload) -> InboundMessage:
        return InboundMessage(
            channel=Channel.WHATSAPP,
            channel_identifier=payload.from_.strip().lstrip("+"),
            display_name=payload.profile_name,
            text=payload.text,
            provider=str(payload.metadata.get("provider", "whatsapp")),
            external_message_id=payload.message_id,
            correlation_id=str(payload.metadata.get("correlation_id") or new_id("corr")),
            metadata=payload.metadata,
            profile_metadata={"phone": payload.from_.strip()},
        )
