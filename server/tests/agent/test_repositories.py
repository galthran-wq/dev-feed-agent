from uuid import uuid4

from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.profiles import PROFILE_SECTIONS
from src.repositories.agent_messages import AgentMessageRepository
from src.repositories.connections import ConnectionRepository
from src.repositories.feed_items import FeedItemRepository
from src.repositories.profiles import ProfileRepository


async def test_profile_section_patch_and_render(db_session: AsyncSession) -> None:
    repo = ProfileRepository(db_session)
    user_id = uuid4()

    assert await repo.is_built(user_id) is False

    await repo.set_section(user_id, "Summary", "Backend engineer.")
    await repo.set_section(user_id, "Languages & stacks", "Python, Go.")

    md = await repo.get_markdown(user_id)
    assert "## Summary\n\nBackend engineer." in md
    assert "Python, Go." in md
    # Every canonical section is rendered, in order.
    assert [s for s in PROFILE_SECTIONS if f"## {s}" in md] == PROFILE_SECTIONS

    await repo.mark_built(user_id)
    assert await repo.is_built(user_id) is True

    # Patching one section leaves the others intact.
    await repo.set_section(user_id, "Summary", "Now ML engineer.")
    md2 = await repo.get_markdown(user_id)
    assert "Now ML engineer." in md2
    assert "Python, Go." in md2


async def test_feed_item_dedup(db_session: AsyncSession) -> None:
    repo = FeedItemRepository(db_session)
    user_id = uuid4()

    await repo.add(
        user_id,
        source="github",
        item_type="repo",
        external_id="owner/name",
        url="https://github.com/owner/name",
        title="A repo",
    )

    keys = [("github", "owner/name"), ("arxiv", "2401.00001"), ("github", "owner/other")]
    unseen = await repo.filter_unseen(user_id, keys)
    assert ("github", "owner/name") not in unseen
    assert ("arxiv", "2401.00001") in unseen
    assert ("github", "owner/other") in unseen

    assert await repo.filter_unseen(user_id, []) == set()
    assert await repo.count(user_id) == 1


async def test_agent_message_history_roundtrip(db_session: AsyncSession) -> None:
    repo = AgentMessageRepository(db_session)
    user_id = uuid4()

    run1 = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[TextPart(content="hello")]),
    ]
    run2 = [
        ModelRequest(parts=[UserPromptPart(content="any rust news?")]),
        ModelResponse(parts=[TextPart(content="here you go")]),
    ]
    await repo.append(user_id, ModelMessagesTypeAdapter.dump_json(run1))
    await repo.append(user_id, ModelMessagesTypeAdapter.dump_json(run2))

    # Whole runs concatenated, chronological, tool/turn structure preserved.
    loaded = await repo.load(user_id)
    assert len(loaded) == 4
    assert isinstance(loaded[0], ModelRequest)
    assert isinstance(loaded[-1], ModelResponse)

    # max_runs keeps only the most recent runs (the latest, here run2).
    recent = await repo.load(user_id, max_runs=1)
    assert len(recent) == 2
    assert recent[0].parts[0].content == "any rust news?"

    # A tiny token budget still keeps at least the newest run.
    budgeted = await repo.load(user_id, max_tokens=1)
    assert len(budgeted) == 2
    assert budgeted[0].parts[0].content == "any rust news?"


async def test_agent_message_reset_and_compact(db_session: AsyncSession) -> None:
    repo = AgentMessageRepository(db_session)
    user_id = uuid4()
    run = [ModelRequest(parts=[UserPromptPart(content="hi")]), ModelResponse(parts=[TextPart(content="yo")])]
    await repo.append(user_id, ModelMessagesTypeAdapter.dump_json(run))

    # /reset clears everything.
    await repo.clear(user_id)
    assert await repo.load(user_id) == []

    # /compact collapses history to a single system note carrying the summary.
    await repo.append(user_id, ModelMessagesTypeAdapter.dump_json(run))
    await repo.replace_with_summary(user_id, "User likes Rust; shown 3 repos.")
    collapsed = await repo.load(user_id)
    assert len(collapsed) == 1
    assert "User likes Rust" in collapsed[0].parts[0].content


async def test_mark_profile_build_started_stamps_timestamp(db_session: AsyncSession) -> None:
    repo = ConnectionRepository(db_session)
    conn = await repo.get_or_create(uuid4())
    assert conn.last_profile_build_at is None

    await repo.mark_profile_build_started(conn)
    assert conn.last_profile_build_at is not None
    # The stamp was committed and survives a reload.
    reloaded = await repo.get_by_user_id(conn.user_id)
    assert reloaded is not None
    assert reloaded.last_profile_build_at is not None


async def test_telegram_link_is_single_use_and_no_hijack(db_session: AsyncSession) -> None:
    repo = ConnectionRepository(db_session)
    conn = await repo.get_or_create(uuid4())
    code = conn.telegram_link_code

    linked = await repo.link_telegram(code, "chat-1")
    assert linked is not None
    assert linked.telegram_chat_id == "chat-1"

    # The original code was rotated on success -> it cannot be reused.
    assert await repo.link_telegram(code, "chat-evil") is None

    # An already-linked connection won't be silently re-pointed to a different chat.
    assert await repo.link_telegram(linked.telegram_link_code, "chat-evil") is None

    # Re-linking the same chat with the current code is idempotent and allowed.
    assert await repo.link_telegram(linked.telegram_link_code, "chat-1") is not None
