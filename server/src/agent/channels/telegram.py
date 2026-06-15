"""Telegram output channel: shared bot, message chunking, the TelegramChannel adapter.
Inbound updates are a separate concern — see services/telegram.py."""

import html
import re
from functools import lru_cache
from typing import Any

import structlog
from src.core.config import settings

logger = structlog.get_logger()

_TELEGRAM_LIMIT = 4096

# Surfaced to the agent (via deps.channel.format_instructions) so it composes messages in the
# markup Telegram actually renders. Telegram HTML supports only a small tag set.
_TELEGRAM_FORMAT = (
    "This channel renders **Telegram HTML**. Format every message as HTML using ONLY these tags: "
    "<b>bold</b>, <i>italic</i>, <u>underline</u>, <s>strikethrough</s>, <code>inline code</code>, "
    "<pre>code block</pre>, <blockquote>quote</blockquote>, and inline links "
    '<a href="https://...">anchor text</a>.\n'
    "- Embed every link INLINE as an <a> with descriptive anchor text (usually the item's name or "
    "title) — never paste a bare URL on its own line.\n"
    "- Use <b> for section/category headings and for item titles.\n"
    "- Do NOT use Markdown (*, _, #, backticks, [text](url)), tables, or any tag not listed above.\n"
    "- Escape a literal < or > in visible text as &lt; / &gt; (e.g. writing 'a &lt; b'). You do "
    "NOT need to escape & in URLs — that's handled for you. Leave your real tags unescaped.\n"
    "- Emojis are welcome for visual structure."
)

# Only Telegram's own tags — so the plain-text fallback strips formatting without eating a
# literal '<' in text (e.g. "if x<3"), which is itself a common cause of the parse failure.
_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|a|tg-spoiler|span)(?:\s[^>]*)?>", re.IGNORECASE
)
# Ampersands that aren't already an entity: the usual reason an unescaped URL (?a=1&b=2) makes
# Telegram reject the whole HTML message. Fixed server-side so we don't rely on the LLM.
_BARE_AMP_RE = re.compile(r"&(?!#?\w+;)")
# Detect text that is already Telegram HTML (e.g. the feed digest) so we don't double-process it.
_HTML_TAG_RE = re.compile(r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|a|tg-spoiler|span)\b", re.I)
_MD_CODE_RE = re.compile(r"`([^`\n]+)`")
_MD_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_MD_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")


def _fix_bare_amps(text: str) -> str:
    return _BARE_AMP_RE.sub("&amp;", text)


def _to_telegram_html(text: str) -> str:
    """The model often answers in Markdown — especially on the no-send fallback path — which
    Telegram's HTML mode renders literally (raw ``**`` and backticks). If the text isn't already
    HTML, escape it and convert the common Markdown tokens (bold, code, links) to Telegram tags."""
    if _HTML_TAG_RE.search(text):
        return text  # already HTML (e.g. the feed digest) — leave it
    t = html.escape(text, quote=False)  # neutralize & < > in the prose first
    t = _MD_CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", t)
    t = _MD_BOLD_RE.sub(r"<b>\1</b>", t)
    t = _MD_LINK_RE.sub(r'<a href="\2">\1</a>', t)
    return t


def _strip_tags(text: str) -> str:
    """Plain-text fallback: drop Telegram tags and decode entities so a parse failure still
    delivers readable text instead of raw <a href=…> markup."""
    return html.unescape(_TAG_RE.sub("", text))


@lru_cache(maxsize=1)
def get_bot() -> Any:
    if not settings.telegram_enabled:
        raise RuntimeError("Telegram bot token is not configured")
    from aiogram import Bot  # lazy: importing this module must not pull in the transport

    if settings.telegram_proxy:
        from aiogram.client.session.aiohttp import AiohttpSession

        return Bot(token=settings.telegram_bot_token, session=AiohttpSession(proxy=settings.telegram_proxy))
    return Bot(token=settings.telegram_bot_token)


def _chunks(text: str, limit: int = _TELEGRAM_LIMIT) -> list[str]:
    out: list[str] = []
    # None (not "") for "empty buffer" so blank lines survive — dropping them merges paragraphs.
    buf: str | None = None
    for line in text.split("\n"):
        candidate = line if buf is None else f"{buf}\n{line}"
        if len(candidate) <= limit:
            buf = candidate
            continue
        if buf is not None:
            out.append(buf)
        while len(line) > limit:
            out.append(line[:limit])
            line = line[limit:]
        buf = line
    if buf is not None:
        out.append(buf)
    return out or [""]


class TelegramChannel:
    format_instructions = _TELEGRAM_FORMAT

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        from aiogram.exceptions import TelegramBadRequest  # lazy: keep aiogram out of import time

        bot = get_bot()
        for chunk in _chunks(text):
            rendered = _fix_bare_amps(_to_telegram_html(chunk))
            try:
                await bot.send_message(self.chat_id, rendered, parse_mode="HTML", disable_web_page_preview=True)
            except TelegramBadRequest as exc:
                # A 400 means the HTML was malformed (a stray <, a tag split across chunks) and the
                # message was NOT delivered — so here, and only here, resend it tag-stripped so the
                # content isn't lost. Network/flood errors propagate to upstream containment; retrying
                # them could double-send a message Telegram may already have delivered.
                logger.warning("telegram_html_send_failed", chat_id=self.chat_id, error=str(exc))
                await bot.send_message(self.chat_id, _strip_tags(rendered), disable_web_page_preview=True)


async def setup_webhook() -> None:
    bot = get_bot()
    await bot.set_webhook(
        url=settings.telegram_webhook_url,
        secret_token=settings.telegram_webhook_secret,
        allowed_updates=["message"],
        drop_pending_updates=True,
    )
    logger.info("telegram_webhook_set", url=settings.telegram_webhook_url)


async def remove_webhook() -> None:
    try:
        bot = get_bot()
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.session.close()
        logger.info("telegram_webhook_deleted")
    except Exception as exc:
        logger.warning("telegram_webhook_delete_failed", error=str(exc))
    finally:
        get_bot.cache_clear()
