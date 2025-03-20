from datetime import datetime
from typing import Optional

from bot_detector.database import Base
from sqlalchemy import JSON, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column


class HighscoreData(Base):
    __tablename__ = "highscore_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scrape_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    start_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scrape_year: Mapped[int] = mapped_column(Integer, nullable=False)
    scrape_week: Mapped[int] = mapped_column(Integer, nullable=False)
    skills: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)
    activities: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)
    skills_delta: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)
    activities_delta: Mapped[Optional[dict[str, int]]] = mapped_column(
        JSON, nullable=True
    )
