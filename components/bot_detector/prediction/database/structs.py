from datetime import datetime
from typing import Any, Optional

from bot_detector.core.database import Base
from sqlalchemy import DECIMAL, JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class PredictionLatestStruct(Base):
    __tablename__ = "prediction_latest"

    created_at: Mapped[datetime] = mapped_column(DateTime)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Players.id"), primary_key=True
    )
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    prediction: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(DECIMAL(5, 4), nullable=False)
    predictions: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)


class PredictionStruct(Base):
    __tablename__ = "prediction"

    prediction_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Players.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    prediction: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(DECIMAL(5, 4), nullable=False)
    predictions: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
