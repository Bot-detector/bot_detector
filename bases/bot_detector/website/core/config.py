import pathlib

import dotenv
from bot_detector.website.app.controllers.bot_detector import BotDetector
from bot_detector.website.app.controllers.patreon import Patreon
from bot_detector.website.core.fastapi.middelware import https_url_for
from fastapi.templating import Jinja2Templates
from pydantic import Field
from pydantic_settings import BaseSettings

dotenv.load_dotenv()


class Settings(BaseSettings):
    BD_TOKEN: str = Field(default=...)
    ENV: str = Field(default="PRD")
    RELEASE_VERSION: str = Field(default="0.1")
    PATREON_CLIENT_ID: str = Field(default="")
    PATREON_CLIENT_SECRET: str = Field(default="")


BD_API = BotDetector(token=Settings().BD_TOKEN)

PATREON = Patreon(
    client_id=Settings().PATREON_CLIENT_ID,
    client_secret=Settings().PATREON_CLIENT_SECRET,
)

current_dir = pathlib.Path(__file__).parent
parent_dir = current_dir.parent
templates_dir = pathlib.Path(parent_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)

if Settings().ENV != "DEV":
    templates.env.globals["url_for"] = https_url_for.https_url_for
