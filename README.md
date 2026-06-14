# devfeed.fyi

A personalized, **agentic news feed for developers & ML engineers**. Connect your GitHub and the
agent learns what you build, then watches GitHub, HuggingFace, Hacker News, arXiv and Reddit and
delivers a curated feed — projects, good-first-issues, help-wanted tickets, papers, models and
discussions — straight to Telegram. Chat with it to steer what you see.

## What makes it different

It's a **lightweight agent**, not a recommendation engine or another keyword digest:

- **Wired to real dev sources over MCP** — GitHub, HuggingFace, Hacker News, arXiv and Reddit
  (plus optional Perplexity), each a live MCP toolset the agent queries directly, not a scraped cache.
- **A personal profile it builds and maintains** — a living markdown `profile.md`, inferred from your
  GitHub activity (your repos and their dependencies) and self-edited as it learns more. Relevance is
  the LLM *reasoning over this profile*.
- **Memory** — it remembers your conversations and everything it has already shown you, so the feed
  never repeats and the way you steer it sticks.
- **A scheduled feed** — an hourly pass curates fresh, de-duplicated items and delivers them to
  Telegram. Chat anytime to dig deeper or change direction.

## How it works

1. **Connect with GitHub** (OAuth) on the landing page — that's the entire web UI.
2. The agent builds your **`profile.md`** by exploring your repos and their dependencies (an
   Explore-style sub-agent). It's a sectioned markdown document the agent maintains itself — it
   patches a section whenever it learns something new or you state a preference.
3. **Link Telegram** with one tap. From then on everything happens there.
4. An hourly job **curates a feed** across all sources, balancing *exploitation* (your known
   interests) with *exploration* (adjacent new horizons), de-dups against what you've already seen,
   and delivers the top matches.

---

**Running it?** → [`deploy/README.md`](deploy/README.md) — setup, configuration, and operations.
