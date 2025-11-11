from datetime import datetime
from typing import Any, Optional

from bot_detector.database import Base
from sqlalchemy import (
    DECIMAL,
    JSON,
    TIMESTAMP,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
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


class PredictionsTableStruct(Base):
    __tablename__ = "Predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(12))
    prediction = Column(String(50))
    created = Column(TIMESTAMP)
    predicted_confidence = Column(DECIMAL(5, 2))
    real_player = Column(DECIMAL(5, 2), default=0)
    pvm_melee_bot = Column(DECIMAL(5, 2), default=0)
    smithing_bot = Column(DECIMAL(5, 2), default=0)
    magic_bot = Column(DECIMAL(5, 2), default=0)
    fishing_bot = Column(DECIMAL(5, 2), default=0)
    mining_bot = Column(DECIMAL(5, 2), default=0)
    crafting_bot = Column(DECIMAL(5, 2), default=0)
    pvm_ranged_magic_bot = Column(DECIMAL(5, 2), default=0)
    pvm_ranged_bot = Column(DECIMAL(5, 2), default=0)
    hunter_bot = Column(DECIMAL(5, 2), default=0)
    fletching_bot = Column(DECIMAL(5, 2), default=0)
    clue_scroll_bot = Column(DECIMAL(5, 2), default=0)
    lms_bot = Column(DECIMAL(5, 2), default=0)
    agility_bot = Column(DECIMAL(5, 2), default=0)
    wintertodt_bot = Column(DECIMAL(5, 2), default=0)
    runecrafting_bot = Column(DECIMAL(5, 2), default=0)
    zalcano_bot = Column(DECIMAL(5, 2), default=0)
    woodcutting_bot = Column(DECIMAL(5, 2), default=0)
    thieving_bot = Column(DECIMAL(5, 2), default=0)
    soul_wars_bot = Column(DECIMAL(5, 2), default=0)
    cooking_bot = Column(DECIMAL(5, 2), default=0)
    vorkath_bot = Column(DECIMAL(5, 2), default=0)
    barrows_bot = Column(DECIMAL(5, 2), default=0)
    herblore_bot = Column(DECIMAL(5, 2), default=0)
    zulrah_bot = Column(DECIMAL(5, 2), default=0)
    gauntlet_bot = Column(DECIMAL(5, 2), default=0)
    nex_bot = Column(DECIMAL(5, 2), default=0)
    unknown_bot = Column(DECIMAL(5, 2), default=0)
