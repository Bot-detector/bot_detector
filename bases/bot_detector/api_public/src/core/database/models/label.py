from bot_detector.api_public.src.core.database.database import Base
from sqlalchemy import Column, Integer, Text


class Label(Base):
    __tablename__ = "Labels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(Text)
