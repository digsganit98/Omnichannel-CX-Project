from shared.schemas.messages import Channel, InboundMessage, WebChatWebhookPayload
from shared.utils.ids import new_id

from .base import ChannelAdapter


class WebChatAdapter(ChannelAdapter):
    def normalize(self, payload: WebChatWebhookPayload) -> InboundMessage:
        session_id = payload.session_id.strip()
        return InboundMessage(
            channel=Channel.WEB_CHAT,
            channel_identifier=f"web_session:{session_id}",
            display_name=payload.display_name,
            text=payload.text,
            provider=str(payload.metadata.get("provider", "web_chat")),
            external_message_id=payload.message_id,
            correlation_id=str(payload.metadata.get("correlation_id") or new_id("corr")),
            metadata=payload.metadata,
            profile_metadata={"web_session_id": session_id},
        )
