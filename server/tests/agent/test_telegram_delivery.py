import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from src.agent.channels import telegram as tg
from src.agent.channels.base import CollectingChannel
from src.agent.channels.telegram import _chunks, _fix_bare_amps, _strip_tags, _to_telegram_html


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


def test_strip_tags_keeps_literal_angle_brackets() -> None:
    # Only real Telegram tags are stripped; a literal < in text (the very thing that often
    # triggers the parse failure) must survive the fallback, not be eaten.
    assert _strip_tags("if x<3 and y>2") == "if x<3 and y>2"
    assert _strip_tags("<b>x</b> y<z") == "x y<z"


def test_fix_bare_amps_escapes_only_non_entities() -> None:
    assert _fix_bare_amps("https://x/a?b=1&c=2") == "https://x/a?b=1&amp;c=2"
    assert _fix_bare_amps("already &amp; fine &#39;q&#39;") == "already &amp; fine &#39;q&#39;"


def test_to_telegram_html_converts_markdown() -> None:
    # The fallback-path markdown the user saw: **bold** and `code`.
    assert _to_telegram_html("честно искал, вернули **пусто**") == "честно искал, вернули <b>пусто</b>"
    assert _to_telegram_html("два вызова `find_github_issues`") == "два вызова <code>find_github_issues</code>"
    assert (
        _to_telegram_html("see [UniFace](https://github.com/x/y)") == 'see <a href="https://github.com/x/y">UniFace</a>'
    )


def test_to_telegram_html_escapes_plain_specials() -> None:
    assert _to_telegram_html("if x < 3 && y") == "if x &lt; 3 &amp;&amp; y"


def test_to_telegram_html_leaves_existing_html_untouched() -> None:
    # The feed digest is already HTML — don't double-process it.
    digest = '🤖 <b>LLMs</b>\n• <a href="https://x">GLM</a> — open model'
    assert _to_telegram_html(digest) == digest


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


async def test_send_falls_back_to_plain_on_bad_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_plain: list[str] = []

    class FakeBot:
        async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None, **_: object) -> None:
            if parse_mode == "HTML":
                raise TelegramBadRequest(method=None, message="can't parse entities")  # type: ignore[arg-type]
            sent_plain.append(text)

    monkeypatch.setattr(tg, "get_bot", lambda: FakeBot())
    await tg.TelegramChannel("1").send('<b>Hi</b> &amp; <a href="u">link</a>')
    # content delivered, tags stripped + entities decoded
    assert sent_plain == ["Hi & link"]


async def test_send_does_not_double_send_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    class FakeBot:
        async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None, **_: object) -> None:
            nonlocal calls
            calls += 1
            raise TelegramNetworkError(method=None, message="timeout")  # type: ignore[arg-type]

    monkeypatch.setattr(tg, "get_bot", lambda: FakeBot())
    # A network error may mean the message WAS delivered — must propagate, not retry (no double-send).
    with pytest.raises(TelegramNetworkError):
        await tg.TelegramChannel("1").send("hi")
    assert calls == 1
