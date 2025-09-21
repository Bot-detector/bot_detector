import logging

from bot_detector.api_ml.core.config import get_models
from fastapi import APIRouter, Depends, HTTPException, status
from mlflow.exceptions import MlflowException
from mlflow.pyfunc import PyFuncModel

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/models")
def list_models(models: dict = Depends(get_models)):
    return {"models": list(models.keys())}


@router.get("/models/{model_name}")
def get_model_info(model_name: str, models: dict = Depends(get_models)):
    model: PyFuncModel | None = models.get(model_name, None)

    if model is None:
        raise HTTPException(status_code=404, detail=f"Model: {model_name} not found")

    _model = model._model_impl.python_model
    info = {}
    if model._model_meta is not None:
        if (
            hasattr(model._model_meta, "run_id")
            and model._model_meta.run_id is not None
        ):
            info["run_id"] = model._model_meta.run_id
        if (
            hasattr(model._model_meta, "artifact_path")
            and model._model_meta.artifact_path is not None
        ):
            info["artifact_path"] = model._model_meta.artifact_path
        info["flavor"] = model._model_meta.flavors

    return {
        "model": model_name,
        "status": "loaded",
        "input_example": model.input_example,
        "model_info": info,
        "input_schema": _model.get_input_json_schema(),
        "output_schema": _model.get_output_json_schema(),
    }


@router.post("/models/{model_name}/predict")
def predict(
    model_name: str,
    data: list[dict],
    models: dict[str, PyFuncModel] = Depends(get_models),
):
    model = models.get(model_name, None)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model: {model_name} not found")
    try:
        prediction = model.predict(data)
    except MlflowException as e:
        logger.error(e.json_kwargs)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=e.serialize_as_json()
        )
    except Exception as e:
        logger.error("heyaaa")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"model": model_name, "prediction": prediction}
