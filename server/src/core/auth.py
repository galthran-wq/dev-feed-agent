from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.database import get_postgres_session
from src.models.postgres import UserModel
from src.repositories.users import UserRepository

security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash"""
    return bool(pwd_context.verify(plain_password, hashed_password))


def get_password_hash(password: str) -> str:
    """Generate password hash"""
    return str(pwd_context.hash(password))


def create_access_token(data: dict[str, object], expires_delta: timedelta | None = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)

    to_encode.update({"exp": expire})
    encoded_jwt: str = jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def create_token_for_user(user: UserModel) -> str:
    token_data: dict[str, object] = {
        "sub": str(user.id),
        "email": user.email,
        "is_verified": user.is_verified,
        "is_superuser": user.is_superuser,
    }
    return create_access_token(token_data)


def decode_jwt_token(token: str) -> tuple[bool, UUID | None, str | None]:
    """
    Decode JWT token and extract user ID
    Returns: (success, user_id, error_message)
    """
    try:
        payload: dict[str, object] = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id_str = payload.get("sub")

        if not isinstance(user_id_str, str):
            return False, None, "Could not validate credentials"

        user_id = UUID(user_id_str)
        return True, user_id, None

    except JWTError:
        return False, None, "Could not validate credentials"
    except ValueError:
        return False, None, "Could not validate credentials"


async def validate_user_from_token(
    token: str, postgres_session: AsyncSession
) -> tuple[bool, UserModel | None, str | None]:
    """
    Validate JWT token and return user
    Returns: (success, user, error_message)
    """
    success, user_id, error = decode_jwt_token(token)
    if not success or user_id is None:
        return False, None, error

    user_repo = UserRepository(postgres_session)
    user = await user_repo.get_user(user_id)

    if user is None:
        return False, None, "Could not validate credentials"

    return True, user, None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    postgres_session: AsyncSession = Depends(get_postgres_session),
) -> UserModel:
    """Get the current user from JWT token"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    success, user, error = await validate_user_from_token(credentials.credentials, postgres_session)

    if not success or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_id(user: UserModel = Depends(get_current_user)) -> UUID:
    """Get the current user ID (for backward compatibility)"""
    return user.id


async def get_current_superuser(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    """Get the current superuser, raises 403 if not a superuser"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions. Superuser access required."
        )
    return current_user
