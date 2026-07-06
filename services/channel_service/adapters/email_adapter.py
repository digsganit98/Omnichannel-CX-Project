from shared.schemas.messages import Channel, EmailWebhookPayload, InboundMessage
from shared.utils.ids import new_id

from .base import ChannelAdapter


class EmailAdapter(ChannelAdapter):
    def normalize(self, payload: EmailWebhookPayload) -> InboundMessage:
        text = f"{payload.subject}\n\n{payload.body}".strip()
        return InboundMessage(
            channel=Channel.EMAIL,
            channel_identifier=payload.from_email.strip().lower(),
            display_name=payload.from_email,
            subject=payload.subject,
            text=text,
            provider=str(payload.metadata.get("provider", "email")),
            external_message_id=payload.message_id,
            correlation_id=str(payload.metadata.get("correlation_id") or new_id("corr")),
            metadata=payload.metadata,
            profile_metadata={"email": payload.from_email.strip().lower()},
        )
