import logging

from bot_detector.api_ml.core.config import get_models
from fastapi import APIRouter, Depends, HTTPException
from mlflow.pyfunc import PyFuncModel

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/models")
def list_models(models: dict = Depends(get_models)):
    return {"models": list(models.keys())}


@router.get("/models/{model_name}")
def get_model_info(model_name: str, models: dict = Depends(get_models)):
    model = models.get(model_name, None)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model: {model_name} not found")
    return {"model": model, "status": "loaded"}


@router.post("/models/{model_name}/predict")
def predict(
    model_name: str,
    data: list[dict],
    models: dict[str, PyFuncModel] = Depends(get_models),
):
    model = models.get(model_name, None)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model: {model_name} not found")
    prediction = model.predict(data)
    return {"model": model_name, "prediction": prediction}
