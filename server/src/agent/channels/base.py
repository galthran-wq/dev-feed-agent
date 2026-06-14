"""The Channel port: where an agent run sends user-facing text (via the send_message tool)."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Channel(Protocol):
    async def send(self, text: str) -> None: ...


class CollectingChannel:
    """Buffers sent messages in memory — for the HTTP /message response and for tests."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)
