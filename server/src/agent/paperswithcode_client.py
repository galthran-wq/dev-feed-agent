"""Minimal async client for Papers with Code (paperswithcode.co) trending papers.

A clean JSON API (no scraping): the trending feed returns papers with their abstract,
categories, linked code repos (with star counts), and HuggingFace artifacts. Returns
plain dicts — the tool shapes them into compact text for the model.
"""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_API = "https://paperswithcode.co/api/v1/papers/"


class PapersWithCodeClient:
    async def trending(self, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch the current trending papers, most-trending first."""
        params: dict[str, str] = {
            "page": "1",
            "page_size": str(limit),
            "order_by": "trending",
            "order_dir": "desc",
            "time": "all_time",
            "latest_only": "true",
            "include_resources": "true",
        }
        async with httpx.AsyncClient(timeout=20.0, headers={"Accept": "application/json"}) as client:
            resp = await client.get(_API, params=params)
            resp.raise_for_status()
            data = resp.json()
        return [_summarize(p) for p in data.get("results", [])[:limit]]


def _best_url(p: dict[str, Any]) -> str | None:
    arxiv_id = p.get("arxiv_id")
    return f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else p.get("url_abs")


def _top_repo(p: dict[str, Any]) -> dict[str, Any] | None:
    """The most-starred linked repo — the code that makes a paper actionable."""
    repos = p.get("repositories") or []
    if not repos:
        return None
    best = max(repos, key=lambda r: r.get("num_stars") or 0)
    return {"url": best.get("url"), "stars": best.get("num_stars"), "official": best.get("is_official")}


def _summarize(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_id": p.get("id"),
        "title": p.get("title"),
        "url": _best_url(p),
        "arxiv_id": p.get("arxiv_id"),
        "published": p.get("published"),
        "categories": p.get("all_categories", []),
        # tldr is usually absent; fall back to the abstract, truncated to stay compact.
        "summary": (p.get("tldr") or p.get("abstract") or "")[:300],
        "citation_count": p.get("citation_count"),
        "top_repo": _top_repo(p),
        "hf_model": (p.get("hf_artifact_summary") or {}).get("best_url"),
    }
