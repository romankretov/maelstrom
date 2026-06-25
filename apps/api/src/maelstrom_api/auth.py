import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .models import User


async def get_user_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID], None]:
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    def __init__(self, user_db: SQLAlchemyUserDatabase[User, uuid.UUID]) -> None:
        super().__init__(user_db)
        secret = get_settings().api_secret_key.get_secret_value()
        self.reset_password_token_secret = secret
        self.verification_token_secret = secret

    async def on_after_register(
        self,
        user: User,
        request: Any | None = None,
    ) -> None:
        # First registered user becomes the admin/superuser. We pull the
        # session off the SQLAlchemyUserDatabase (the concrete impl) — the
        # base Protocol doesn't expose it, hence the cast.
        from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

        from .models.user import Role

        assert isinstance(self.user_db, SQLAlchemyUserDatabase)
        session = self.user_db.session
        count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        if count == 1:
            user.is_superuser = True
            user.role = Role.ADMIN
            session.add(user)
            await session.commit()


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy[User, uuid.UUID]:
    return JWTStrategy(
        secret=get_settings().api_secret_key.get_secret_value(),
        lifetime_seconds=60 * 60 * 8,  # 8 hours; TOTP step-up required for sensitive ops
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
