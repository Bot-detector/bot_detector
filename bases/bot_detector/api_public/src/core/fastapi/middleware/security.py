import re

from bot_detector.api_public.src.core.fastapi.dependencies import wide_event
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

UA_PATTERN = r"^RuneLite/\d+\.\d+\.\d+.*"
ua_re = re.compile(UA_PATTERN)

MAX_BODY_PREVIEW = 100


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ua = request.headers.get("user-agent", "")
        path = request.url.path

        # only enforce on report endpoint
        if path == "/v2/report":
            if not ua_re.match(ua):
                body_preview = (await request.body())[:MAX_BODY_PREVIEW].decode(
                    errors="replace"
                )
                wide_event.add_context(
                    {
                        "security": "Invalid UserAgent",
                        "body_preview": body_preview,
                    }
                )
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})

        return await call_next(request)
