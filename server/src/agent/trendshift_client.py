"""Minimal async client for Trendshift (trendshift.io) trending GitHub repos.

Trendshift has no public JSON API — the only documented endpoint returns a badge
image. But every period page publishes its ranking as schema.org JSON-LD (an
``ItemList`` of ``SoftwareSourceCode``), which the site maintains for SEO, so it is
far more stable than scraping rendered markup. We fetch the page and parse that.
Returns plain dicts — the tool shapes them into compact text for the model.
"""

import json
import re
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_BASE = "https://trendshift.io"
# Period -> page path. Daily momentum lives at the site root.
PERIODS: dict[str, str] = {"daily": "/", "weekly": "/weekly", "monthly": "/monthly"}
_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
# Identifiable, polite UA — the page is public/server-rendered, but say who we are.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; dev-feed-agent/1.0; +https://github.com/galthran-wq/dev-feed-agent)"
}


class TrendshiftClient:
    async def trending(self, period: str = "daily", limit: int = 25) -> list[dict[str, Any]]:
        """Fetch the trending repos for ``period`` (daily/weekly/monthly), newest rank first."""
        path = PERIODS.get(period, PERIODS["daily"])
        async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
            resp = await client.get(f"{_BASE}{path}")
            resp.raise_for_status()
            html = resp.text
        elements = _parse_item_list(html)
        return [_summarize(el) for el in elements[:limit]]


def _parse_item_list(html: str) -> list[dict[str, Any]]:
    """Return the JSON-LD ItemList's ``ListItem`` elements (each has position, url, item)."""
    for block in _LD_RE.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            return [el for el in data.get("itemListElement", []) if isinstance(el.get("item"), dict)]
    return []


def _summarize(el: dict[str, Any]) -> dict[str, Any]:
    """Map one JSON-LD ListItem to the compact repo dict the gather sub-agent reads.

    ``el`` looks like::

        {
          "position": 1,
          "url": "https://trendshift.io/repositories/20881",
          "item": {
            "name": "owner/repo",
            "description": "...",
            "programmingLanguage": "Python",
            "codeRepository": "https://github.com/owner/repo",
            "url": "https://github.com/owner/repo",
            "author": {"name": "owner", "url": "..."},
            "keywords": ["AI agent", ...],
            "dateCreated": "...", "dateModified": "...",
          },
        }

    Mirror the shape of ``github_client._repo_summary`` so the sub-agent treats
    Trendshift and GitHub repos uniformly — at minimum it needs a stable id
    (``full_name``), a GitHub ``url``, the ``rank`` (the whole point of Trendshift),
    and enough context (description/language) to judge relevance. Truncate the
    description like ``_repo_summary`` does (200 chars) to keep the payload compact.
    """
    item = el.get("item", {})
    return {
        "rank": el.get("position"),
        "full_name": item.get("name"),
        "description": (item.get("description") or "")[:200],
        "language": item.get("programmingLanguage"),
        "url": item.get("codeRepository") or item.get("url"),
        "author": (item.get("author") or {}).get("name"),
        "keywords": item.get("keywords", []),
        "trendshift_url": el.get("url"),
    }
