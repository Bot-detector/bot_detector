# script to insert all the data we need
import random
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
random.seed(42)

# Define other SQLAlchemy models for remaining tables in a similar manner

# Create an engine and bind the base
engine = create_engine("mysql+pymysql://root:root_bot_buster@mysql:3306/playerdata")
Base.metadata.create_all(engine)

# Create a session
Session = sessionmaker(bind=engine)
session = Session()


class Labels(Base):
    __tablename__ = "Labels"

    id = Column(Integer, primary_key=True)
    label = Column(String)


class Players(Base):
    __tablename__ = "Players"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    possible_ban = Column(Boolean, default=True)
    confirmed_ban = Column(Boolean, default=False)
    confirmed_player = Column(Boolean, default=False)
    label_id = Column(Integer)
    label_jagex = Column(Integer)
    # ironman = Column(Boolean)
    # hardcore_ironman = Column(Boolean)
    # ultimate_ironman = Column(Boolean)
    normalized_name = Column(String)


class Report(Base):
    __tablename__ = "Reports"

    ID = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP)
    reportedID = Column(Integer)
    reportingID = Column(Integer)
    region_id = Column(Integer)
    x_coord = Column(Integer)
    y_coord = Column(Integer)
    z_coord = Column(Integer)
    timestamp = Column(TIMESTAMP)
    manual_detect = Column(SmallInteger)
    on_members_world = Column(Integer)
    on_pvp_world = Column(SmallInteger)
    world_number = Column(Integer)
    equip_head_id = Column(Integer)
    equip_amulet_id = Column(Integer)
    equip_torso_id = Column(Integer)
    equip_legs_id = Column(Integer)
    equip_boots_id = Column(Integer)
    equip_cape_id = Column(Integer)
    equip_hands_id = Column(Integer)
    equip_weapon_id = Column(Integer)
    equip_shield_id = Column(Integer)
    equip_ge_value = Column(BigInteger)


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
