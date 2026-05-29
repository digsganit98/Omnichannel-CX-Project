from abc import ABC, abstractmethod

from shared.schemas.messages import InboundMessage


class ChannelAdapter(ABC):
    @abstractmethod
    def normalize(self, payload) -> InboundMessage:
        raise NotImplementedError
