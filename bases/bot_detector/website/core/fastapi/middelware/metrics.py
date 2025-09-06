import time

from fastapi import Request
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

# Define Prometheus metrics
REQUEST_COUNT = Counter(
    "request_count", "Total number of requests", ["method", "endpoint", "http_status"]
)
REQUEST_LATENCY = Histogram(
    "request_latency_seconds", "Latency of requests in seconds", ["method", "endpoint"]
)


# Middleware for Prometheus metrics logging
class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Start timer for request latency
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate request latency
        latency = time.time() - start_time

        # Update Prometheus metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            http_status=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path,
        ).observe(latency)

        return response
