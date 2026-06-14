"""The agent's only way to talk to the user.

``send_message`` writes to ``deps.channel`` (a Telegram chat, a buffered HTTP response,
a test sink). The agent's turn produces no user-visible output otherwise — there is no
returned-reply path anymore — so a turn that should answer MUST call this. It may be
called multiple times to send progress updates or several messages.
"""

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
        # No delivery target (e.g. profile build on first OAuth connect, before any chat
        # is linked). Not an error — the message simply has nowhere to go this run.
        logger.warning("send_message_no_channel", user_id=str(ctx.deps.user_id))
        return "no channel configured; message not sent"
    await ctx.deps.channel.send(text)
    ctx.deps.sent_count += 1
    return "sent"


MESSAGING_TOOLS = [send_message]
