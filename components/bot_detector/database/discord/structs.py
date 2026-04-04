from datetime import datetime

from bot_detector.database import Base
from pydantic import BaseModel
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class DiscordVerificationTable(Base):
    __tablename__ = "DiscordVerification"

    Entry: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Discord_id: Mapped[str] = mapped_column(String(255))
    Player_id: Mapped[int] = mapped_column(Integer)
    primary_rsn: Mapped[int] = mapped_column(Integer, default=0)
    Code: Mapped[str] = mapped_column(String(255))
    verified_status: Mapped[int] = mapped_column(Integer, default=0)
    token_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class DiscordVerificationStruct(BaseModel):
    Entry: int | None = None
    Discord_id: str | None = None
    Player_id: int | None = None
    primary_rsn: bool | None = None
    Code: str | None = None
    verified_status: int | None = None
    token_used: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
