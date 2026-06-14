from types import SimpleNamespace
from uuid import uuid4

from src.agent.channels import CollectingChannel
from src.agent.deps import AgentDeps
from src.agent.tools.messaging_tools import send_message


async def test_collecting_channel_buffers() -> None:
    ch = CollectingChannel()
    await ch.send("a")
    await ch.send("b")
    assert ch.messages == ["a", "b"]


async def test_send_message_writes_to_channel_and_counts() -> None:
    ch = CollectingChannel()
    deps = AgentDeps(session=None, user_id=uuid4(), channel=ch)  # type: ignore[arg-type]
    ctx = SimpleNamespace(deps=deps)

    assert await send_message(ctx, "  hello  ") == "sent"  # type: ignore[arg-type]
    assert ch.messages == ["hello"]
    assert deps.sent_count == 1


async def test_send_message_empty_is_ignored() -> None:
    ch = CollectingChannel()
    deps = AgentDeps(session=None, user_id=uuid4(), channel=ch)  # type: ignore[arg-type]
    ctx = SimpleNamespace(deps=deps)
    assert await send_message(ctx, "   ") == "empty text ignored"  # type: ignore[arg-type]
    assert ch.messages == []
    assert deps.sent_count == 0


async def test_send_message_no_channel_does_not_raise() -> None:
    deps = AgentDeps(session=None, user_id=uuid4(), channel=None)  # type: ignore[arg-type]
    ctx = SimpleNamespace(deps=deps)
    # Never raises — the message simply has nowhere to go (e.g. profile build pre-link).
    assert "not sent" in await send_message(ctx, "hi")  # type: ignore[arg-type]
    assert deps.sent_count == 0
