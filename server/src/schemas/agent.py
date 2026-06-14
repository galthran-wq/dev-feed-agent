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


class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    # The agent talks via send_message; over HTTP those messages are collected and returned.
    messages: list[str]
