from bot_detector.database.api.interface import ApiUserInterface
from bot_detector.database.api.structs import (
    ApiPermissionTableStruct,
    ApiUsageTableStruct,
    ApiUserPermTableStruct,
    ApiUserTableStruct,
)
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession


class ApiUserRepo(ApiUserInterface):
    async def log_usage(
        self,
        async_session: AsyncSession,
        user_id: int,
        route: str,
        auto_commit: bool = True,
    ) -> None:
        query = insert(ApiUsageTableStruct).values(
            user_id=user_id,
            route=route,
        )
        await async_session.execute(query)
        if auto_commit:
            await async_session.commit()

    async def has_permission(
        self,
        async_session: AsyncSession,
        permission: str,
        token: str,
        user_name: str | None = None,
        user_id: int | None = None,
    ) -> bool:
        if not user_name and user_id is None:
            raise ValueError("user_name or user_id is required")
        api_user = ApiUserTableStruct
        api_user_perms = ApiUserPermTableStruct
        api_permissions = ApiPermissionTableStruct
        query = (
            select(api_user_perms)
            .join(api_user, api_user_perms.user_id == api_user.id)
            .join(api_permissions, api_user_perms.permission_id == api_permissions.id)
            .where(api_user.token == token)
            .where(api_permissions.permission == permission)
        )
        if user_name is not None:
            query = query.where(api_user.username == user_name)
        if user_id is not None:
            query = query.where(api_user.id == user_id)
        query = query.limit(1)

        result = await async_session.execute(query)
        row = result.scalar_one_or_none()
        return row is not None

    async def get_user(
        self,
        async_session: AsyncSession,
        user_name: str,
        is_active: bool | None = None,
    ) -> ApiUserTableStruct | None:
        if not user_name:
            raise ValueError("user_name is required")
        query = select(ApiUserTableStruct).where(
            ApiUserTableStruct.username == user_name,
        )
        if is_active is not None:
            query = query.where(ApiUserTableStruct.is_active == is_active)
        result = await async_session.execute(query)
        return result.scalar_one_or_none()
