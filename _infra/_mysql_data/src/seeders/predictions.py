import random
from collections.abc import Generator

from pydantic import BaseModel

PREDICTION_LABELS = [
    "Unknown",
    "Real_Player",
    "Wintertodt_bot",
    "Mining_bot",
    "Hunter_bot",
    "Herblore_bot",
    "Fletching_bot",
    "Fishing_bot",
    "Crafting_bot",
    "Cooking_bot",
    "Woodcutting_bot",
    "Smithing_bot",
    "Magic_bot",
    "PVM_Ranged_Magic_bot",
    "Agility_bot",
    "Zalcano_bot",
    "Runecrafting_bot",
    "PVM_Ranged_bot",
    "PVM_Melee_bot",
    "Thieving_bot",
    "LMS_bot",
    "Soul_Wars_bot",
    "Vorkath_bot",
    "Clue_Scroll_bot",
    "Barrows_bot",
    "Zulrah_bot",
    "Gauntlet_bot",
    "Nex_bot",
    "Unknown_bot",
]


class PredictionLatest(BaseModel):
    player_id: int
    model_name: str
    prediction: str
    confidence: float
    predictions: dict[str, float] | None = None


def create_predictions(
    player_ids: list[int], count: int
) -> Generator[PredictionLatest, None, None]:
    if count > len(player_ids):
        player_ids = player_ids * (count // len(player_ids) + 1)

    selected_ids = player_ids[:count]

    for player_id in selected_ids:
        prediction = random.choice(PREDICTION_LABELS)
        confidence = round(random.uniform(0.5, 0.99), 4)

        predictions_dict = {}
        remaining = 1.0 - confidence
        for label in PREDICTION_LABELS:
            if label == prediction:
                predictions_dict[label] = confidence
            else:
                partial = round(random.uniform(0, remaining / 10), 4)
                predictions_dict[label] = partial

        yield PredictionLatest(
            player_id=player_id,
            model_name="multi_model_v1",
            prediction=prediction,
            confidence=confidence,
            predictions=predictions_dict,
        )
