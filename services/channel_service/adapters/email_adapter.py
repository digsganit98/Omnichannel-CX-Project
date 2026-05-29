from shared.schemas.messages import Channel, EmailWebhookPayload, InboundMessage

from .base import ChannelAdapter


class EmailAdapter(ChannelAdapter):
    def normalize(self, payload: EmailWebhookPayload) -> InboundMessage:
        text = f"{payload.subject}\n\n{payload.body}".strip()
        return InboundMessage(
            channel=Channel.EMAIL,
            customer_id=f"email:{payload.from_email.lower()}",
            display_name=payload.from_email,
            subject=payload.subject,
            text=text,
            external_message_id=payload.message_id,
            metadata=payload.metadata,
        )
