from bot_detector.structs.prediction import PredictionCreate


class PredictionsToInsertStruct(PredictionCreate):
    """Message shape for the `predictions.to_insert` topic.

    Carries a single ML prediction to be inserted into the
    `prediction` and `prediction_latest` tables.
    """
