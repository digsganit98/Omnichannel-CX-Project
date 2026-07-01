from __future__ import annotations

import importlib
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass

from shared.schemas.messages import Channel, InboundMessage


@dataclass(frozen=True)
class OutboundMessage:
    to_id: str
    text: str


class BaseChannelAdapter(ABC):
    channel: Channel | str

    @abstractmethod
    def parse_inbound(self, payload: dict) -> InboundMessage:
        raise NotImplementedError

    @abstractmethod
    async def send_outbound(self, message: OutboundMessage) -> dict:
        raise NotImplementedError


class ChannelAdapterRegistry:
    _adapters: dict[str, BaseChannelAdapter] = {}
    _discovered = False

    @classmethod
    def discover(cls) -> None:
        if cls._discovered:
            return
        for module in pkgutil.iter_modules(__path__):
            if not module.name.startswith("_"):
                importlib.import_module(f"{__name__}.{module.name}")
        for adapter_cls in BaseChannelAdapter.__subclasses__():
            cls.register(adapter_cls())
        cls._discovered = True

    @classmethod
    def register(cls, adapter: BaseChannelAdapter) -> None:
        channel = adapter.channel.value if isinstance(adapter.channel, Channel) else adapter.channel
        cls._adapters[channel] = adapter

    @classmethod
    def get(cls, channel: Channel | str) -> BaseChannelAdapter:
        cls.discover()
        key = channel.value if isinstance(channel, Channel) else channel
        return cls._adapters[key]
