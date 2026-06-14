"""Concrete output channels — the delivery-side adapters for the agent's send_message.

The agent layer defines the abstract :class:`src.agent.channels.Channel`; this module is
the services-side counterpart that implements it over a real transport. Today that's just
Telegram; a future web/SSE channel would live here too.
"""

from src.services import notifier


class TelegramChannel:
    """A :class:`src.agent.channels.Channel` that delivers to one Telegram chat.

    Structural-typed (no explicit base) so the agent layer never imports services.
    """

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        await notifier.send_text(self.chat_id, text)
