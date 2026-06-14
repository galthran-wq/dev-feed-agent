"""Output channel abstraction: *where* an agent run sends messages.

The agent no longer returns a reply string for someone else to deliver. Instead it emits
user-facing text as a side effect via the ``send_message`` tool, which writes to
``deps.channel``. A channel hides the transport (a Telegram chat, a buffered HTTP
response, a test sink) behind one ``async send()``, so chat, the scheduled feed, and the
profile build all "talk" the same way and Telegram/web are just adapters at the edges.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Channel(Protocol):
    """Anything an agent run can send user-facing text to."""

    async def send(self, text: str) -> None: ...


class CollectingChannel:
    """In-memory channel that buffers everything sent.

    Used by the synchronous HTTP ``POST /api/agent/message`` (the messages become the
    response body) and by tests that assert on what the agent produced.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)
