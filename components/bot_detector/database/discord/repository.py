import logging
from datetime import datetime

from bot_detector.database.discord.interface import DiscordVerificationInterface
from bot_detector.database.discord.structs import (
    DiscordVerificationStruct,
    DiscordVerificationTableStruct,
)
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DiscordVerificationRepo(DiscordVerificationInterface):
    async def get_verified_player(
        self,
        async_session: AsyncSession,
        discord_id: str | None = None,
        player_id: int | None = None,
        is_verified: bool | None = None,
    ) -> DiscordVerificationStruct | None:
        query = select(DiscordVerificationTableStruct)
        
        if discord_id is not None:
            query = query.where(DiscordVerificationTableStruct.Discord_id == discord_id)
        
        if player_id is not None:
            query = query.where(DiscordVerificationTableStruct.Player_id == player_id)
        
        if is_verified is not None:
            query = query.where(DiscordVerificationTableStruct.verified_status == (1 if is_verified else 0))
        
        query = query.where(DiscordVerificationTableStruct.primary_rsn == 1)
        query = query.limit(1)
        
        async with async_session.begin():
            result = await async_session.execute(query)
            row = result.scalar_one_or_none()
            
            if row is None:
                return None
            
            return DiscordVerificationStruct(
                Entry=row.Entry,
                Discord_id=row.Discord_id,
                Player_id=row.Player_id,
                primary_rsn=row.primary_rsn,
                Code=row.Code,
                verified_status=row.verified_status,
                token_used=row.token_used,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    async def get_linked_accounts(
        self,
        async_session: AsyncSession,
        discord_id: str,
    ) -> list[DiscordVerificationStruct]:
        query = (
            select(DiscordVerificationTableStruct)
            .where(DiscordVerificationTableStruct.Discord_id == discord_id)
            .where(DiscordVerificationTableStruct.verified_status == 1)
            .order_by(DiscordVerificationTableStruct.Entry.desc())
        )
        
        async with async_session.begin():
            result = await async_session.execute(query)
            rows = result.scalars().all()
            
            return [
                DiscordVerificationStruct(
                    Entry=row.Entry,
                    Discord_id=row.Discord_id,
                    Player_id=row.Player_id,
                    primary_rsn=row.primary_rsn,
                    Code=row.Code,
                    verified_status=row.verified_status,
                    token_used=row.token_used,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    async def create_verification(
        self,
        async_session: AsyncSession,
        discord_id: str,
        player_id: int,
        code: str,
    ) -> DiscordVerificationStruct:
        query = insert(DiscordVerificationTableStruct).values(
            Discord_id=discord_id,
            Player_id=player_id,
            Code=code,
            primary_rsn=0,
            verified_status=0,
            token_used=0,
        )
        
        async with async_session.begin():
            await async_session.execute(query)
            await async_session.commit()
            
            return DiscordVerificationStruct(
                Discord_id=discord_id,
                Player_id=player_id,
                Code=code,
                primary_rsn=False,
                verified_status=0,
                token_used=0,
            )

    async def update_verification_status(
        self,
        async_session: AsyncSession,
        discord_id: str,
        player_id: int,
        verified_status: int,
    ) -> bool:
        query = (
            update(DiscordVerificationTableStruct)
            .where(DiscordVerificationTableStruct.Discord_id == discord_id)
            .where(DiscordVerificationTableStruct.Player_id == player_id)
            .values(
                verified_status=verified_status,
                updated_at=datetime.now(),
            )
        )
        
        async with async_session.begin():
            result = await async_session.execute(query)
            await async_session.commit()
            
            return result.rowcount > 0

    async def set_primary_rsn(
        self,
        async_session: AsyncSession,
        discord_id: str,
        player_id: int,
        is_primary: bool,
    ) -> bool:
        clear_query = (
            update(DiscordVerificationTableStruct)
            .where(DiscordVerificationTableStruct.Discord_id == discord_id)
            .values(primary_rsn=0)
        )
        
        set_query = (
            update(DiscordVerificationTableStruct)
            .where(DiscordVerificationTableStruct.Discord_id == discord_id)
            .where(DiscordVerificationTableStruct.Player_id == player_id)
            .values(primary_rsn=1 if is_primary else 0, updated_at=datetime.now())
        )
        
        async with async_session.begin():
            await async_session.execute(clear_query)
            result = await async_session.execute(set_query)
            await async_session.commit()
            
            return result.rowcount > 0
