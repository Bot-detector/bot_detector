from mlflow.pyfunc import PyFuncModel
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MLFLOW_S3_ENDPOINT_URL: str = Field(default=...)
    AWS_ACCESS_KEY_ID: str = Field(default=...)
    AWS_SECRET_ACCESS_KEY: str = Field(default=...)
    MODEL_URIS: dict[str, str] = Field(default=...)


def get_models() -> dict[str, PyFuncModel]:
    return models


models: dict = {}
SETTINGS = Settings()
