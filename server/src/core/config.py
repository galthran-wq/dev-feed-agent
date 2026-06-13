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

    @property
    def is_debug(self) -> bool:
        return self.log_level.lower() in ("debug", "info")

    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


settings = Settings()
