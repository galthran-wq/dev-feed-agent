from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    app_name: str = "dev-feed-agent"
    log_level: str = "info"
    cors_origins: list[str] = ["http://localhost:5677"]
    metrics_enabled: bool = True

    postgres_user: str = "postgres"
    postgres_password: str = "password"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "webapp"

    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 24 * 60

    # Fernet key for encrypting stored secrets at rest; distinct from SECRET_KEY. Empty => plaintext.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str = ""

    app_base_url: str = "http://localhost:5677"

    # --- GitHub OAuth (the only sign-in path) ---
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    github_oauth_scopes: str = "read:user public_repo"

    # --- LLM agent (pydantic-ai via OpenRouter) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    agent_model: str = "deepseek/deepseek-v4-pro"
    # Optional heavier model for the profile_build sub-agent; falls back to agent_model.
    profile_builder_model: str = ""

    # --- Telegram bot (delivery + interactive chat) ---
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    # Echoed back by Telegram in X-Telegram-Bot-Api-Secret-Token; verified on every webhook.
    telegram_webhook_secret: str = ""
    # Route the bot's HTTP through a proxy — for hosts where api.telegram.org is egress-blocked
    # but the rest of the internet is fine. Empty => direct.
    telegram_proxy: str = ""

    # --- MCP feed sources ---
    hf_mcp_url: str = "https://huggingface.co/mcp"
    hf_token: str = ""
    mcp_hn_url: str = ""
    mcp_arxiv_url: str = ""
    mcp_reddit_url: str = ""
    # Cost-aware: meant mainly for explicit "go deeper" chat queries.
    mcp_perplexity_url: str = ""
    perplexity_api_key: str = ""
    # Unreachable sources are dropped (logged) instead of aborting the whole run.
    mcp_probe_timeout: float = 5.0

    # --- Observability (Pydantic Logfire; opt-in) ---
    # Write token for the app to SEND traces; empty => tracing off (app runs normally).
    # The read token (for querying traces, e.g. the MCP) is a separate credential.
    logfire_token: str = ""
    logfire_base_url: str = "https://logfire-eu.pydantic.dev"
    logfire_environment: str = "production"

    # --- Feed curation ---
    discovery_enabled: bool = True
    poll_interval_minutes: int = 60
    # No fixed feed size: the agent surfaces every fresh, relevant item that clears the quality
    # bar (one compact line each), leaning exploit with some explore — see prompts/chat.md.
    agent_history_token_budget: int = 12000

    # --- Long-term memory (mem0, OSS over pgvector; LLM + embeddings via OpenRouter) ---
    mem0_chat_model: str = "deepseek/deepseek-v4-flash"
    mem0_embed_model: str = "qwen/qwen3-embedding-8b"
    # qwen3 is matryoshka (max 4096) — truncated to this via the OpenAI `dimensions` param.
    # Keep <=2000: pgvector's HNSW index rejects more.
    mem0_embed_dims: int = 1024
    mem0_search_limit: int = 5

    @property
    def agent_enabled(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def telegram_webhook_url(self) -> str:
        return f"{self.app_base_url.rstrip('/')}/api/telegram/webhook"

    @property
    def perplexity_enabled(self) -> bool:
        # Gateway URL is the source of truth: the key is injected into the gateway, not used here.
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
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


settings = Settings()
