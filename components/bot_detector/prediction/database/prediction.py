from bot_detector.core.database import Base
from sqlalchemy import DECIMAL, JSON, TIMESTAMP, Column, Integer, String


class Prediction_v1(Base):
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


class Prediction_v2(Base):
    __tablename__ = "prediction_latest"

    created_at = Column(TIMESTAMP)
    player_id = Column(Integer, primary_key=True)
    model_name = Column(String(50))
    prediction = Column(String(50))
    confidence = Column(DECIMAL(5, 2))
    predictions = Column(JSON)
