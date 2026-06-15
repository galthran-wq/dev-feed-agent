import asyncio

import httpx
import pytest
from src.agent import github_client as gc


async def test_search_retries_on_secondary_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # GitHub 403s bursty/concurrent search (the fan-out's failure mode). _search must retry,
    # not surface an error that the agent reads as "no issues".
    client = gc.GithubClient("tok")
    calls = {"n": 0}
    req = httpx.Request("GET", "https://api.github.com/search/issues")

    async def fake_get(path: str, params: object = None) -> object:
        calls["n"] += 1
        if calls["n"] < 3:  # first two attempts hit the secondary limit
            resp = httpx.Response(403, headers={}, request=req)
            raise httpx.HTTPStatusError("secondary rate limit", request=req, response=resp)
        return {"items": [{"id": 1, "title": "t", "html_url": "u", "repository_url": "/repos/a/b", "labels": []}]}

    async def no_sleep(_d: float) -> None:
        return None

    monkeypatch.setattr(client, "_get", fake_get)
    monkeypatch.setattr(gc.asyncio, "sleep", no_sleep)

    items = await client.search_issues('label:"good first issue" is:open')
    assert calls["n"] == 3  # retried twice, then succeeded
    assert len(items) == 1 and items[0]["repo_full_name"] == "a/b"


async def test_search_gate_serializes_concurrent_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    # The gate must prevent concurrent GitHub search requests (GitHub forbids them per user).
    client = gc.GithubClient("tok")
    concurrent = {"now": 0, "max": 0}

    async def fake_get(path: str, params: object = None) -> object:
        concurrent["now"] += 1
        concurrent["max"] = max(concurrent["max"], concurrent["now"])
        await asyncio.sleep(0)  # yield so overlap would show if unserialized
        concurrent["now"] -= 1
        return {"items": []}

    monkeypatch.setattr(client, "_get", fake_get)
    await asyncio.gather(*(client.search_issues("q") for _ in range(5)))
    assert concurrent["max"] == 1  # never more than one in flight
