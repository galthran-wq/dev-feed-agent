import httpx
import pytest
from src.agent import trendshift_client as tc

# A trimmed copy of the real JSON-LD Trendshift embeds on its trending pages, wrapped
# in the surrounding markup the parser must skip past. Two items is enough to cover
# ranking, the GitHub-url field, and the description.
_PAGE = """
<html><head>
<script type="application/ld+json">{"@type":"WebSite","name":"Trendshift"}</script>
<script type="application/ld+json">{"@type":"ItemList","itemListElement":[
  {"@type":"ListItem","position":1,"url":"https://trendshift.io/repositories/20881",
   "item":{"@type":"SoftwareSourceCode","name":"chopratejas/headroom",
     "description":"Compress tool outputs before they reach the LLM.",
     "codeRepository":"https://github.com/chopratejas/headroom",
     "url":"https://github.com/chopratejas/headroom","programmingLanguage":"Python",
     "author":{"@type":"Person","name":"chopratejas"},"keywords":["AI agent"]}},
  {"@type":"ListItem","position":2,"url":"https://trendshift.io/repositories/10050",
   "item":{"@type":"SoftwareSourceCode","name":"google-research/timesfm",
     "description":"A pretrained time-series foundation model.",
     "codeRepository":"https://github.com/google-research/timesfm",
     "url":"https://github.com/google-research/timesfm","programmingLanguage":"Python",
     "author":{"@type":"Person","name":"google-research"},"keywords":[]}}
]}</script>
</head><body></body></html>
"""


def test_parse_item_list_extracts_ranked_repos() -> None:
    elements = tc._parse_item_list(_PAGE)
    assert [el["position"] for el in elements] == [1, 2]
    assert elements[0]["item"]["name"] == "chopratejas/headroom"


def test_parse_item_list_skips_other_ld_and_bad_json() -> None:
    # The WebSite block (wrong @type) and a malformed block must not break parsing.
    assert tc._parse_item_list("") == []
    assert tc._parse_item_list('<script type="application/ld+json">{bad</script>') == []


def test_summarize_shapes_repo_for_the_agent() -> None:
    el = tc._parse_item_list(_PAGE)[0]
    repo = tc._summarize(el)
    # Stable id, GitHub url, rank, and relevance context must survive the mapping.
    assert repo["full_name"] == "chopratejas/headroom"
    assert repo["url"] == "https://github.com/chopratejas/headroom"
    assert repo["rank"] == 1
    assert repo["language"] == "Python"
    assert repo["description"]


def test_summarize_truncates_long_description() -> None:
    el = {"position": 1, "url": "t", "item": {"name": "a/b", "description": "x" * 500}}
    assert len(tc._summarize(el)["description"]) <= 200


async def test_trending_fetches_and_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text=_PAGE)

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    repos = await tc.TrendshiftClient().trending("weekly", limit=1)
    assert captured["url"] == "https://trendshift.io/weekly"  # period -> path mapping
    assert len(repos) == 1 and repos[0]["full_name"] == "chopratejas/headroom"
