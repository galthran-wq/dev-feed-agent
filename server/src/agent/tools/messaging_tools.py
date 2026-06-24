"""The send_message tool — the agent's only way to reach the user (writes to deps.channel).
The function docstring below is the LLM-facing tool description — keep it."""

import structlog
from pydantic_ai import RunContext
from src.agent.deps import AgentDeps

logger = structlog.get_logger()


async def send_message(ctx: RunContext[AgentDeps], text: str) -> str:
    """Send a message to the user. This is the ONLY way to deliver text to them.

    Call it whenever you want to say something (an answer, a progress note, the feed
    digest, a 'profile is ready' confirmation). You may call it more than once.
    """
    text = (text or "").strip()
    if not text:
        return "empty text ignored"
    if ctx.deps.channel is None:
        # No target yet (e.g. profile build on OAuth connect, before a chat is linked) — not an error.
        logger.warning("send_message_no_channel", user_id=str(ctx.deps.user_id))
        return "no channel configured; message not sent"
    await ctx.deps.channel.send(text)
    ctx.deps.sent_count += 1
    ctx.deps.sent_texts.append(text)
    return "sent"


MESSAGING_TOOLS = [send_message]
