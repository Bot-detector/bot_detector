from datetime import datetime

from bot_detector.database import Base
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class DiscordVerificationTableStruct(Base):
    __tablename__ = "DiscordVerification"

    Discord_id: Mapped[str] = mapped_column(String(255))
    Player_id: Mapped[int] = mapped_column(Integer)
    Code: Mapped[str] = mapped_column(String(255))
    Entry: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False
    )
    primary_rsn: Mapped[int] = mapped_column(Integer, default=0)
    verified_status: Mapped[int] = mapped_column(Integer, default=0)
    token_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
