from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Skill(Base):
    __tablename__ = "skill"

    skill_id = Column(SmallInteger(), primary_key=True, autoincrement=True)
    skill_name = Column(String(50), nullable=False, unique=True)


class Activity(Base):
    __tablename__ = "activity"

    activity_id = Column(SmallInteger(), primary_key=True, autoincrement=True)
    activity_name = Column(String(50), nullable=False, unique=True)


class PlayerSkill(Base):
    __tablename__ = "player_skill"

    player_skill_id = Column(BigInteger(), primary_key=True, autoincrement=True)
    skill_id = Column(SmallInteger(), nullable=False)
    skill_value = Column(Integer(), nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("skill_id", "skill_value", name="unique_skill_value"),
    )


class PlayerActivity(Base):
    __tablename__ = "player_activity"

    player_activity_id = Column(BigInteger(), primary_key=True, autoincrement=True)
    activity_id = Column(SmallInteger(), nullable=False)
    activity_value = Column(Integer(), nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("activity_id", "activity_value", name="unique_activity_value"),
    )


class ScraperDataV3(Base):
    __tablename__ = "scraper_data_v3"

    scrape_id = Column(BigInteger(), primary_key=True, autoincrement=True)
    scrape_ts = Column(DateTime, nullable=False)
    scrape_date = Column(Date, nullable=False)
    player_id = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("player_id", "scrape_date", name="unique_player_scrape"),
        Index("idx_scrape_ts", "scrape_ts"),
    )


class ScraperPlayerSkill(Base):
    __tablename__ = "scraper_player_skill"

    scrape_id = Column(
        BigInteger(),
        ForeignKey("scraper_data_v3.scrape_id"),
        primary_key=True,
    )
    player_skill_id = Column(
        BigInteger(),
        ForeignKey("player_skill.player_skill_id"),
        primary_key=True,
    )

    __table_args__ = (
        Index("idx_scrape_id", "scrape_id"),
        Index("idx_player_skill_id", "player_skill_id"),
    )


class ScraperPlayerActivity(Base):
    __tablename__ = "scraper_player_activity"

    scrape_id = Column(
        BigInteger(),
        ForeignKey("scraper_data_v3.scrape_id"),
        primary_key=True,
    )
    player_activity_id = Column(
        BigInteger(),
        ForeignKey("player_activity.player_activity_id"),
        primary_key=True,
    )

    __table_args__ = (
        Index("idx_scrape_id", "scrape_id"),
        Index("idx_player_activity_id", "player_activity_id"),
    )
