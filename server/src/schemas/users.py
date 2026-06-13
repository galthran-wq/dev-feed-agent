from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr


def _validate_password_length(v: str) -> str:
    if len(v) < 6:
        raise ValueError("Password must be at least 6 characters long")
    return v


Password = Annotated[str, AfterValidator(_validate_password_length)]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None = None
    is_verified: bool
    is_superuser: bool
    created_at: datetime


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: Password


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: Password


class CreateUserResponse(BaseModel):
    success: bool
    message: str
    user: UserResponse | None = None


class DeleteUserRequest(BaseModel):
    user_identifier: UUID | EmailStr


class DeleteUserResponse(BaseModel):
    success: bool
    message: str
