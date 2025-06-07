from sqlalchemy import Boolean, Column, DateTime, Integer, Text
from src.core.database.database import Base

class Player(Base):
    __tablename__ = "Players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    possible_ban = Column(Boolean)
    confirmed_ban = Column(Boolean)
    confirmed_player = Column(Boolean)
    label_id = Column(Integer)
    label_jagex = Column(Integer)
    ironman = Column(Boolean)
    hardcore_ironman = Column(Boolean)
    ultimate_ironman = Column(Boolean)
    normalized_name = Column(Text)
