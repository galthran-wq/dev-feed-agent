from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.profiles import PROFILE_SECTIONS
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
