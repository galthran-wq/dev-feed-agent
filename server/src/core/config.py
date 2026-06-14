from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    app_name: str = "dev-feed-agent"
    log_level: str = "info"
    cors_origins: list[str] = ["http://localhost:5746"]
    metrics_enabled: bool = True

    postgres_user: str = "postgres"
    postgres_password: str = "password"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "webapp"

    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 24 * 60

    # Optional urlsafe-base64 32-byte Fernet key for encrypting secrets at rest
    # (e.g. the stored GitHub access token). Distinct from SECRET_KEY. Empty =>
    # tokens are stored as plaintext (opt-in, like everything else in this app).
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str = ""

    # Public URL of the app — used to build the GitHub OAuth callback and the
    # post-login redirect back to the SPA, and the Telegram deep link.
    app_base_url: str = "http://localhost:5746"

    # --- GitHub OAuth (the only sign-in path for dev-feed-agent) ---
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    github_oauth_scopes: str = "read:user public_repo"

    # --- LLM agent (pydantic-ai via OpenRouter, OpenAI-compatible API) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    agent_model: str = "anthropic/claude-sonnet-4.6"
    # Optional heavier model for the /init profile-builder sub-agent; falls back to agent_model.
    profile_builder_model: str = ""

    # --- Telegram bot (delivery + interactive chat) ---
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""

    # --- MCP feed sources ---
    # HuggingFace is a remote HTTP MCP; the others are gateway containers (supergateway).
    hf_mcp_url: str = "https://huggingface.co/mcp"
    hf_token: str = ""
    mcp_hn_url: str = ""
    mcp_arxiv_url: str = ""
    mcp_reddit_url: str = ""
    # Perplexity is an optional, API-key-gated web-grounded source (the official
    # @perplexity-ai/mcp-server, a stdio server re-exposed via the mcp-perplexity gateway
    # container). Cost-aware: meant mainly for explicit "go deeper" chat queries. Opt-in —
    # skipped unless its gateway URL is configured.
    mcp_perplexity_url: str = ""
    perplexity_api_key: str = ""
    # Seconds to wait when probing each MCP source before a run; unreachable sources are
    # dropped (logged) instead of aborting the whole run. Probes run concurrently.
    mcp_probe_timeout: float = 5.0

    # --- Feed curation ---
    discovery_enabled: bool = True
    poll_interval_minutes: int = 60
    feed_size: int = 8
    # Share of each feed reserved for exploration (new horizons) vs exploitation (known interests).
    explore_ratio: float = 0.3
    # Token budget for replayed agent conversation history (the rest is trimmed oldest-first).
    agent_history_token_budget: int = 12000

    @property
    def agent_enabled(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def perplexity_enabled(self) -> bool:
        # The gateway URL is the source of truth (the key is injected into the gateway
        # container, not used by the agent directly); skip the source unless it's set.
        return bool(self.mcp_perplexity_url)

    @property
    def github_oauth_enabled(self) -> bool:
        return bool(self.github_oauth_client_id and self.github_oauth_client_secret)

    @property
    def token_encryption_enabled(self) -> bool:
        return bool(self.token_encryption_key)

    @property
    def profile_model(self) -> str:
        return self.profile_builder_model or self.agent_model

    @property
    def github_redirect_uri(self) -> str:
        return f"{self.app_base_url.rstrip('/')}/api/auth/github/callback"

    @property
    def is_debug(self) -> bool:
        return self.log_level.lower() in ("debug", "info")

    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


settings = Settings()
