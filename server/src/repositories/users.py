from abc import ABC, abstractmethod
from uuid import UUID

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.models.postgres.users import UserModel

logger = structlog.get_logger()


class UserRepositoryInterface(ABC):
    @abstractmethod
    async def create_user(self) -> UserModel:
        pass

    @abstractmethod
    async def get_user(self, user_id: UUID) -> UserModel | None:
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> UserModel | None:
        pass

    @abstractmethod
    async def register_user(self, user_id: UUID, email: str, password_hash: str) -> UserModel:
        pass

    @abstractmethod
    async def create_registered_user(self, email: str, password_hash: str) -> UserModel:
        pass

    @abstractmethod
    async def delete_user(self, user_identifier: UUID | str, deleting_user_id: UUID) -> UserModel:
        pass


class UserRepository(UserRepositoryInterface):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_user(self) -> UserModel:
        db_user = UserModel()
        self.session.add(db_user)
        await self.session.commit()
        await self.session.refresh(db_user)
        return db_user

    async def get_user(self, user_id: UUID) -> UserModel | None:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> UserModel | None:
        result = await self.session.execute(select(UserModel).where(UserModel.email == email))
        return result.scalar_one_or_none()

    async def register_user(self, user_id: UUID, email: str, password_hash: str) -> UserModel:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundError("User not found")

        user.email = email
        user.password_hash = password_hash
        user.is_verified = True

        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            raise ConflictError("Email already registered") from e

        await self.session.refresh(user)
        return user

    async def create_registered_user(self, email: str, password_hash: str) -> UserModel:
        db_user = UserModel(email=email, password_hash=password_hash, is_verified=True, is_superuser=False)
        self.session.add(db_user)

        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            raise ConflictError("Email already registered") from e

        await self.session.refresh(db_user)
        return db_user

    async def delete_user(self, user_identifier: UUID | str, deleting_user_id: UUID) -> UserModel:
        user = None
        if isinstance(user_identifier, UUID):
            user = await self.get_user(user_identifier)
        else:
            try:
                uuid_identifier = UUID(str(user_identifier))
                user = await self.get_user(uuid_identifier)
            except ValueError:
                user = await self.get_user_by_email(str(user_identifier))

        if not user:
            raise NotFoundError("User not found")

        if user.id == deleting_user_id:
            raise ForbiddenError("Cannot delete your own account")

        if user.is_superuser:
            raise ForbiddenError("Cannot delete another superuser account")

        await self.session.delete(user)
        await self.session.commit()

        return user
