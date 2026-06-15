"""The Channel port: where an agent run sends user-facing text (via the send_message tool).

Each channel also declares ``format_instructions`` — what markup it renders — which is surfaced
to the agent so it formats messages correctly for wherever they'll be delivered."""

from typing import Protocol, runtime_checkable

# Plain-text channels (no rich rendering): say so explicitly so the agent doesn't emit markup.
PLAIN_TEXT_INSTRUCTIONS = (
    "This channel renders plain text only. Do not use HTML or Markdown. Put each link on its own line as a bare URL."
)


@runtime_checkable
class Channel(Protocol):
    # What markup this channel renders — injected into the agent's prompt so it formats to match.
    format_instructions: str

    async def send(self, text: str) -> None: ...


class CollectingChannel:
    """Buffers sent messages in memory — for the HTTP /message response and for tests."""

    format_instructions = PLAIN_TEXT_INSTRUCTIONS

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)
