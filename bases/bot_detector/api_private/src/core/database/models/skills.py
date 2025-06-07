from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.mysql import BIGINT, TINYINT

from src.core.database.database import Base


class Skills(Base):
    __tablename__ = "skills"

    skill_id = Column(TINYINT, primary_key=True, autoincrement=True)
    skill_name = Column(String(50), nullable=False)


class PlayerSkills(Base):
    __tablename__ = "player_skills"

    scraper_id = Column(
        BIGINT,
        ForeignKey("scraper_data.scraper_id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id = Column(
        TINYINT,
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_value = Column(Integer, nullable=False, default=0)
