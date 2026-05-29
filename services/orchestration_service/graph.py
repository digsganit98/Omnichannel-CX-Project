from services.agent_assist_service.next_best_action import recommend_next_best_action
from services.conversation_service.conversation_manager import ConversationManager
from services.intent_service.classifier import classify_intent
from services.intent_service.sentiment import detect_sentiment
from services.intent_service.urgency import detect_urgency
from services.retrieval_service.hybrid_search import HybridSearch
from services.ticket_service.ticket_manager import TicketManager
from shared.schemas.conversation import ConversationTurn
from shared.schemas.messages import InboundMessage
from shared.schemas.responses import ChannelResponse
from shared.utils.in_memory_store import store


class OrchestrationGraph:
    def __init__(self) -> None:
        self.conversations = ConversationManager()
        self.retrieval = HybridSearch()
        self.tickets = TicketManager()

    def run(self, message: InboundMessage) -> ChannelResponse:
        conversation = self.conversations.load(message)
        intent = classify_intent(message.text)
        sentiment = detect_sentiment(message.text)
        urgency = detect_urgency(message.text, sentiment)
        result = self.retrieval.search(message.text)

        confidence = result.score if result else 0.0
        should_ticket = confidence < 0.25 or urgency == "high"
        ticket_id = None

        if should_ticket:
            ticket = self.tickets.create_ticket(
                conversation=conversation,
                message=message,
                intent=intent,
                urgency=urgency,
            )
            ticket_id = ticket.ticket_id
            assistant_text = (
                "I have captured your request and created a support ticket. "
                f"Our {ticket.assigned_team.replace('_', ' ')} team will review it."
            )
            store.record_metric("tickets_created")
        else:
            assistant_text = result.answer
            store.record_metric("resolved")

        next_best_action = recommend_next_best_action(intent, sentiment, urgency, ticket_id)
        turn = ConversationTurn(
            channel=message.channel,
            customer_text=message.text,
            assistant_text=assistant_text,
            intent=intent,
            sentiment=sentiment,
            resolved=not should_ticket,
            ticket_id=ticket_id,
        )
        self.conversations.append_turn(conversation, turn)

        return ChannelResponse(
            conversation_id=conversation.conversation_id,
            customer_id=message.customer_id,
            message=assistant_text,
            resolved=not should_ticket,
            intent=intent,
            sentiment=sentiment,
            urgency=urgency,
            confidence=confidence,
            ticket_id=ticket_id,
            next_best_action=next_best_action,
        )
