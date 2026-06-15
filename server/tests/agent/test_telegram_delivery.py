import pytest
from src.agent.channels import telegram as tg
from src.agent.channels.base import CollectingChannel
from src.agent.channels.telegram import _chunks, _strip_tags


def test_chunks_preserves_blank_lines() -> None:
    # Blank lines (paragraph separators) must survive — they're content, not nothing.
    assert _chunks("\nabc") == ["\nabc"]
    assert _chunks("a\n\nb") == ["a\n\nb"]


def test_chunks_respects_limit_and_splits_long_lines() -> None:
    text = "line1\n" + "x" * 25 + "\nline3"
    chunks = _chunks(text, limit=10)
    assert all(len(c) <= 10 for c in chunks)
    # No content lost: the 25 x's all survive across chunks.
    assert "".join(chunks).count("x") == 25


def test_chunks_empty_string() -> None:
    assert _chunks("") == [""]


def test_strip_tags_drops_tags_and_decodes_entities() -> None:
    assert _strip_tags('<b>Hi</b> &amp; <a href="u">link</a>') == "Hi & link"


def test_channel_format_instructions() -> None:
    # Telegram declares HTML with inline links; the HTTP/test channel declares plain text.
    assert "<a href" in tg.TelegramChannel("1").format_instructions
    assert "plain text" in CollectingChannel().format_instructions.lower()


async def test_send_uses_html_parse_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None]] = []

    class FakeBot:
        async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None, **_: object) -> None:
            calls.append((text, parse_mode))

    monkeypatch.setattr(tg, "get_bot", lambda: FakeBot())
    await tg.TelegramChannel("1").send('<b>hi</b> <a href="https://x">x</a>')
    assert calls and calls[0][1] == "HTML"


async def test_send_falls_back_to_plain_on_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_plain: list[str] = []

    class FakeBot:
        async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None, **_: object) -> None:
            if parse_mode == "HTML":
                raise RuntimeError("Bad Request: can't parse entities")
            sent_plain.append(text)

    monkeypatch.setattr(tg, "get_bot", lambda: FakeBot())
    await tg.TelegramChannel("1").send('<b>Hi</b> &amp; <a href="u">link</a>')
    # content delivered, tags stripped + entities decoded
    assert sent_plain == ["Hi & link"]
