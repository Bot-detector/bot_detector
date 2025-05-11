import json
import logging
import sys

# # log formatting
formatter = logging.Formatter(
    json.dumps(
        {
            "ts": "%(asctime)s",
            "name": "%(name)s",
            "function": "%(funcName)s",
            "level": "%(levelname)s",
            "msg": json.dumps("%(message)s"),
        }
    )
)

stream_handler = logging.StreamHandler(sys.stdout)

stream_handler.setFormatter(formatter)

handlers = [stream_handler]

logging.basicConfig(level=logging.DEBUG, handlers=handlers)

# set imported loggers to warning
logging.getLogger("urllib3").setLevel(logging.DEBUG)
logging.getLogger("uvicorn").setLevel(logging.DEBUG)
logging.getLogger("aiomysql").setLevel(logging.ERROR)
logging.getLogger("aiokafka").setLevel(logging.WARNING)

# if settings.ENV == "PRD":
#     uvicorn_error = logging.getLogger("uvicorn.error")
#     uvicorn_error.disabled = True
#     uvicorn_access = logging.getLogger("uvicorn.access")
#     uvicorn_access.disabled = True

# # https://github.com/aio-libs/aiomysql/issues/103
# # https://github.com/coleifer/peewee/issues/2229
# warnings.filterwarnings("ignore", ".*Duplicate entry.*")
