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
    async def get_by_user_name(
        self,
        async_session: AsyncSession,
        user_name: str,
    ) -> ApiUserTableStruct | None:
        api_user = ApiUserTableStruct
        query = (
            select(api_user)
            .where(api_user.username == user_name)
            .where(api_user.is_active == True)  # noqa: E712
            .limit(1)
        )

        async with async_session.begin():
            result = await async_session.execute(query)
            row = result.scalar_one_or_none()
        return row

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
        user_name: str,
        token: str,
        permission: str,
    ) -> bool:
        api_user = ApiUserTableStruct
        api_user_perms = ApiUserPermTableStruct
        api_permissions = ApiPermissionTableStruct
        query = (
            select(api_user_perms)
            .join(api_user, api_user_perms.user_id == api_user.id)
            .join(api_permissions, api_user_perms.permission_id == api_permissions.id)
            .where(api_user.username == user_name)
            .where(api_user.token == token)
            .where(api_permissions.permission == permission)
            .limit(1)
        )

        async with async_session.begin():
            result = await async_session.execute(query)
            row = result.scalar_one_or_none()
        return row is not None
