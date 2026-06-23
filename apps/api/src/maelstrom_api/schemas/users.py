import uuid

from fastapi_users import schemas

from maelstrom_api.models import Role


class UserRead(schemas.BaseUser[uuid.UUID]):
    role: Role
    display_name: str | None = None


class UserCreate(schemas.BaseUserCreate):
    display_name: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    display_name: str | None = None
