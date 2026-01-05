import logging
import random
import time

from bot_detector.api_public.src.core.config import Settings
from bot_detector.api_public.src.core.fastapi.dependencies import wide_event
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        error_occurred = False
        start_time = time.time()
        token = wide_event._log_context.set({})

        query_params = [
            (key, value if key != "token" else "***")
            for key, value in request.query_params.items()
        ]

        wide_event.add_context(
            {
                "http_method": request.method,
                "http_path": request.url.path,
                # "user_agent": request.headers.get("user-agent"),
                "http_query_params": query_params,
            }
        )
        try:
            response = await call_next(request)
            wide_event.add_context(
                {
                    "http_status": response.status_code,
                }
            )
            return response
        except Exception as e:
            error_occurred = True
            wide_event.add_context(
                {
                    "error": True,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "http_status": 500,
                }
            )
            raise e
        finally:
            duration = (time.time() - start_time) * 1000
            wide_event.add_context({"duration_ms": round(duration, 2)})

            final_event = wide_event.get_context()

            # Logic: Keep ALL errors, keep ALL slow requests (>1000ms), sample 1% of successes
            MAX_DURATION_MS = 1000
            SAMPLE_RATE = 0.01

            if error_occurred:
                final_event["log_reason"] = "error_occurred"
                logger.error(final_event)
            elif final_event.get("http_status", 200) >= 400:
                final_event["log_reason"] = "http_error"
                logger.warning(final_event)
            elif duration > MAX_DURATION_MS:
                final_event["log_reason"] = "slow_request"
                logger.warning(final_event)
            elif random.random() < SAMPLE_RATE:  # 1% sample rate for healthy traffic
                final_event["log_reason"] = "sampled_success"
                final_event["sample_rate"] = SAMPLE_RATE
                logger.info(final_event)
            elif Settings().ENV == "DEV":
                final_event["log_reason"] = "dev_logging"
                logger.info(final_event)
            wide_event._log_context.reset(token)
