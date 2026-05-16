from datetime import datetime

from bot_detector.database import Base
from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column


class PlayersTableStruct(Base):
    __tablename__ = "Players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    possible_ban: Mapped[bool] = mapped_column(Boolean)
    confirmed_ban: Mapped[bool] = mapped_column(Boolean)
    confirmed_player: Mapped[bool] = mapped_column(Boolean)
    label_id: Mapped[int] = mapped_column(Integer)
    label_jagex: Mapped[int] = mapped_column(Integer)
    # ironman: Mapped[bool] = mapped_column(Boolean)
    # hardcore_ironman: Mapped[bool] = mapped_column(Boolean)
    # ultimate_ironman: Mapped[bool] = mapped_column(Boolean)
    # normalized_name: Mapped[str] = mapped_column(Text)
