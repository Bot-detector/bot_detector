from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.mysql import BIGINT, TINYINT

from src.core.database.database import Base


class Activities(Base):
    __tablename__ = "activities"

    activity_id = Column(TINYINT, primary_key=True, autoincrement=True)
    activity_name = Column(String(50), nullable=False)


class PlayerActivities(Base):
    __tablename__ = "player_activities"

    scraper_id = Column(
        BIGINT,
        ForeignKey("scraper_data.scraper_id", ondelete="CASCADE"),
        primary_key=True,
    )
    activity_id = Column(
        TINYINT,
        ForeignKey("activities.activity_id", ondelete="CASCADE"),
        primary_key=True,
    )
    activity_value = Column(Integer, nullable=False, default=0)
