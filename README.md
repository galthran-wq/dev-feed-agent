# dev-feed-agent

A personalized, **agentic news feed for developers & ML engineers**. Connect your GitHub and the
agent learns what you build, then watches GitHub, HuggingFace, Hacker News, arXiv and Reddit and
delivers a curated feed — projects, good-first-issues, help-wanted tickets, papers, models and
discussions — straight to Telegram. Chat with it to steer what you see.

## How it works

1. **Connect with GitHub** (OAuth) on the landing page — that's the entire web UI.
2. The agent builds a **profile** of your interests by exploring your repos and their dependencies
   (an Explore-style sub-agent). The profile is a sectioned markdown document the agent maintains
   itself — it patches a section whenever it learns something new or you state a preference.
3. **Link Telegram** with one tap. From then on everything happens there.
4. An hourly job **curates a feed** across all sources, balancing *exploitation* (your known
   interests) with *exploration* (adjacent new horizons), de-dups against what you've already seen,
   and delivers the top matches. Chat anytime to dig deeper or change direction.

The LLM judges relevance by reasoning over your profile — **no embeddings**.

Built on FastAPI + Vue 3 + PostgreSQL, orchestrated with Docker Compose.

---

**Running it?** → [`deploy/README.md`](deploy/README.md) — setup, configuration, and operations.
