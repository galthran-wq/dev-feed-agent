import httpx
import pytest
from src.agent import paperswithcode_client as pwc

# A trimmed copy of the real paperswithcode.co response (two papers: one external with a
# repo, one arXiv paper without repos) — enough to cover url selection, repo picking, and
# the abstract/tldr fallback.
_PAGE = {
    "count": 2,
    "results": [
        {
            "id": "98456",
            "arxiv_id": None,
            "url_abs": "https://z.ai/blog/glm-5.2",
            "title": "GLM-5.2: Built for Long-Horizon Tasks",
            "abstract": "GLM-5.2 is Z.ai's latest flagship open-weight model." * 20,
            "published": "2026-06-16",
            "all_categories": ["cs.CL"],
            "tldr": None,
            "citation_count": 0,
            "repositories": [
                {"url": "https://github.com/thudm/slime", "num_stars": 6737, "is_official": True},
                {"url": "https://github.com/zai-org/glm-5", "num_stars": 5341, "is_official": True},
            ],
            "hf_artifact_summary": {"best_url": "https://huggingface.co/zai-org/GLM-5.2"},
        },
        {
            "id": "555",
            "arxiv_id": "2606.16140",
            "url_abs": "https://paperswithcode.co/paper/555",
            "title": "VibeThinker",
            "abstract": "A small reasoning model.",
            "published": "2026-06-10",
            "all_categories": ["cs.LG"],
            "tldr": "3B model beats much larger ones on math.",
            "citation_count": 5,
            "repositories": [],
            "hf_artifact_summary": {},
        },
    ],
}


def test_summarize_external_paper_picks_top_repo_and_url() -> None:
    s = pwc._summarize(_PAGE["results"][0])
    assert s["external_id"] == "98456"
    assert s["url"] == "https://z.ai/blog/glm-5.2"  # no arxiv_id -> url_abs
    assert s["top_repo"] == {"url": "https://github.com/thudm/slime", "stars": 6737, "official": True}
    assert s["hf_model"] == "https://huggingface.co/zai-org/GLM-5.2"
    assert len(s["summary"]) <= 300  # abstract truncated


def test_summarize_arxiv_paper_prefers_arxiv_url_and_tldr() -> None:
    s = pwc._summarize(_PAGE["results"][1])
    assert s["url"] == "https://arxiv.org/abs/2606.16140"  # arxiv_id wins
    assert s["summary"] == "3B model beats much larger ones on math."  # tldr preferred over abstract
    assert s["top_repo"] is None  # no repos


async def test_trending_fetches_and_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_PAGE)

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    papers = await pwc.PapersWithCodeClient().trending(limit=2)
    assert captured["params"]["order_by"] == "trending"  # asks for the trending feed
    assert [p["title"] for p in papers] == ["GLM-5.2: Built for Long-Horizon Tasks", "VibeThinker"]
