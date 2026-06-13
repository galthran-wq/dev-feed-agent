from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GithubProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    github_username: str | None = None
    # Whether a token is stored — never echo the token itself back to clients.
    has_github_token: bool = False
    telegram_linked: bool = False
    poll_enabled: bool = True
    last_polled_at: datetime | None = None


class UpdateGithubProfileRequest(BaseModel):
    github_username: str | None = None
    github_token: str | None = None
    poll_enabled: bool | None = None


class InterestProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: str = ""
    languages: list[str] = []
    topics: list[str] = []
    keywords: list[str] = []
    updated_at: datetime | None = None


class TelegramLinkResponse(BaseModel):
    linked: bool
    url: str | None = None
    bot_configured: bool = False


class ChatRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime


class ChatResponse(BaseModel):
    reply: str
    interests: InterestProfileResponse


class SentIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repo_full_name: str
    issue_url: str
    title: str
    languages: str | None = None
    stars: int = 0
    relevance: float = 0.0
    reason: str | None = None
    sent_at: datetime


class RebuildProfileResponse(BaseModel):
    interests: InterestProfileResponse
    repos_scanned: int


class PollNowResponse(BaseModel):
    matches_sent: int
    candidates_scanned: int
    message: str
