import re

from bot_detector.api_public.src.core.fastapi.dependencies import wide_event
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

UA_PATTERN = r"^RuneLite/\d+\.\d+\.\d+.*"
ua_re = re.compile(UA_PATTERN)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ua = request.headers.get("user-agent", "")
        path = request.url.path

        # only enforce on report endpoint
        if path == "/v2/report":
            if not ua_re.match(ua):
                wide_event.add_context({"security": "Invalid UserAgent"})
                raise HTTPException(status_code=403, detail="Forbidden")

        return await call_next(request)
