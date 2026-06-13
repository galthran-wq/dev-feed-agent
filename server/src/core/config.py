from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    app_name: str = "WebApp"
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

    # --- Public URL used to build the Telegram deep link shown in the UI ---
    app_base_url: str = "http://localhost:5746"

    # --- LLM agent (pydantic-ai via OpenRouter, OpenAI-compatible API) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    agent_model: str = "anthropic/claude-3.7-sonnet"

    # --- Telegram bot ---
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""

    # --- Discovery scheduler ---
    discovery_enabled: bool = True
    poll_interval_minutes: int = 60
    max_issues_per_poll: int = 100
    max_matches_per_user: int = 5
    # Agent-assigned relevance (0..1) an issue must reach to be delivered.
    relevance_threshold: float = 0.75

    @property
    def agent_enabled(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def is_debug(self) -> bool:
        return self.log_level.lower() in ("debug", "info")

    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


settings = Settings()
