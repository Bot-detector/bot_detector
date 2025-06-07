from sqlalchemy import Column, Date, DateTime, func
from sqlalchemy.dialects.mysql import BIGINT, SMALLINT

from src.core.database.database import Base


class ScraperData(Base):
    __tablename__ = "scraper_data"

    scraper_id = Column(BIGINT, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    player_id = Column(SMALLINT, nullable=False)
    record_date = Column(Date, nullable=True)


class ScraperDataLatest(Base):
    __tablename__ = "scraper_data_latest"

    scraper_id = Column(BIGINT)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    player_id = Column(BIGINT, primary_key=True)
    record_date = Column(Date, nullable=True)
