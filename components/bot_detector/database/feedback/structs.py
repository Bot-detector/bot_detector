from datetime import datetime

from bot_detector.database import Base
from sqlalchemy import (
    TIMESTAMP,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column


class PredictionFeedbackTableStruct(Base):
    __tablename__ = "PredictionsFeedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="CURRENT_TIMESTAMP"
    )
    voter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Players.id"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Players.id"), nullable=False
    )
    prediction: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    vote: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reviewed: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    user_notified: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    feedback_text: Mapped[str | None] = mapped_column(
        Text(collation="utf8mb4_0900_ai_ci"), default=None
    )
    reviewer_id: Mapped[int | None] = mapped_column(Integer, default=None)
    proposed_label: Mapped[str | None] = mapped_column(String(50), default=None)
