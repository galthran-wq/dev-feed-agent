from pydantic import BaseModel


class StatusResponse(BaseModel):
    github_connected: bool
    github_username: str | None = None
    avatar_url: str | None = None
    telegram_linked: bool
    profile_built: bool
    agent_enabled: bool


class TelegramLinkResponse(BaseModel):
    linked: bool
    url: str | None = None
    bot_configured: bool


class RebuildResponse(BaseModel):
    status: str
    message: str


class PollNowResponse(BaseModel):
    delivered: int
    curated: int
    message: str
