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
        query = (
            select(ApiUserTableStruct)
            .where(ApiUserTableStruct.username == user_name)
            .where(ApiUserTableStruct.is_active == True)  # noqa: E712
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
        permission: str,
    ) -> bool:
        query = (
            select(ApiUserPermTableStruct)
            .join(
                ApiUserTableStruct,
                ApiUserPermTableStruct.user_id == ApiUserTableStruct.id,
            )
            .join(
                ApiPermissionTableStruct,
                ApiUserPermTableStruct.permission_id == ApiPermissionTableStruct.id,
            )
            .where(ApiUserTableStruct.username == user_name)
            .where(ApiPermissionTableStruct.permission == permission)
            .limit(1)
        )

        async with async_session.begin():
            result = await async_session.execute(query)
            row = result.scalar_one_or_none()
        return row is not None
