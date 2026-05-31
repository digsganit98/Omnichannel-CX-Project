from services.orchestration_service.graph import OrchestrationGraph
from shared.schemas.messages import InboundMessage
from shared.schemas.responses import ChannelResponse


class OmnichannelRouter:
    def __init__(self, graph: OrchestrationGraph) -> None:
        self.graph = graph

    def handle(self, message: InboundMessage) -> ChannelResponse:
        return self.graph.run(message)
