from datetime import date
from typing import Optional

from bot_detector.database import Base
from sqlalchemy import (
    JSON,
    Computed,
    Date,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
)
from sqlalchemy.orm import Mapped, mapped_column


class HighscoreDataDailyTableStruct(Base):
    __tablename__ = "highscore_data_daily"

    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scrape_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_to_live: Mapped[date] = mapped_column(Date, nullable=False)
    scrape_year: Mapped[int] = mapped_column(
        SmallInteger, Computed("YEAR(scrape_date)"), nullable=False
    )
    scrape_month: Mapped[int] = mapped_column(
        Integer, Computed("MONTH(scrape_date)"), nullable=False
    )
    scrape_week: Mapped[int] = mapped_column(
        Integer, Computed("WEEK(scrape_date, 3)"), nullable=False
    )
    skills: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)
    activities: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (PrimaryKeyConstraint("player_id", "scrape_date"),)


class HighscoreDataWeeklyTableStruct(Base):
    __tablename__ = "highscore_data_weekly"

    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scrape_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_to_live: Mapped[date] = mapped_column(Date, nullable=False)
    scrape_year: Mapped[int] = mapped_column(
        SmallInteger, Computed("YEAR(scrape_date)"), nullable=False
    )
    scrape_month: Mapped[int] = mapped_column(
        Integer, Computed("MONTH(scrape_date)"), nullable=False
    )
    scrape_week: Mapped[int] = mapped_column(
        Integer, Computed("WEEK(scrape_date, 3)"), nullable=False
    )
    skills: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)
    activities: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (PrimaryKeyConstraint("player_id", "scrape_year", "scrape_week"),)


class HighscoreDataMonthlyTableStruct(Base):
    __tablename__ = "highscore_data_monthly"

    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scrape_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_to_live: Mapped[date] = mapped_column(Date, nullable=False)
    scrape_year: Mapped[int] = mapped_column(
        SmallInteger, Computed("YEAR(scrape_date)"), nullable=False
    )
    scrape_month: Mapped[int] = mapped_column(
        Integer, Computed("MONTH(scrape_date)"), nullable=False
    )
    scrape_week: Mapped[int] = mapped_column(
        Integer, Computed("WEEK(scrape_date, 3)"), nullable=False
    )
    skills: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)
    activities: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (PrimaryKeyConstraint("player_id", "scrape_year", "scrape_month"),)


class HighscoreDataLatestTableStruct(Base):
    __tablename__ = "highscore_data_latest"

    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scrape_date: Mapped[date] = mapped_column(Date, nullable=False)
    scrape_year: Mapped[int] = mapped_column(
        SmallInteger, Computed("YEAR(scrape_date)"), nullable=False
    )
    scrape_month: Mapped[int] = mapped_column(
        Integer, Computed("MONTH(scrape_date)"), nullable=False
    )
    scrape_week: Mapped[int] = mapped_column(
        Integer, Computed("WEEK(scrape_date, 3)"), nullable=False
    )
    skills: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)
    activities: Mapped[Optional[dict[str, int]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (PrimaryKeyConstraint("player_id"),)
