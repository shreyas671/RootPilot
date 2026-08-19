import json
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REQUEST_COUNT = Counter(
    "rootpilot_http_requests_total",
    "HTTP requests handled by RootPilot",
    ("method", "route", "status"),
)
REQUEST_LATENCY = Histogram(
    "rootpilot_http_request_duration_seconds",
    "RootPilot HTTP request duration",
    ("method", "route"),
)
REQUESTS_IN_PROGRESS = Gauge(
    "rootpilot_http_requests_in_progress",
    "RootPilot HTTP requests currently executing",
    ("method",),
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in (
            "request_id",
            "method",
            "route",
            "status_code",
            "duration_ms",
            "job_id",
            "incident_id",
        ):
            value = getattr(record, field, None)

            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())


async def observe_request(
    request: Request,
    call_next: object,
) -> Response:
    request_id = request.headers.get(
        "X-Request-ID",
        str(uuid4()),
    )[:128]
    request.state.request_id = request_id
    started_at = time.perf_counter()
    method = request.method
    REQUESTS_IN_PROGRESS.labels(method=method).inc()

    try:
        response = await call_next(request)
    except Exception:
        route = getattr(
            request.scope.get("route"),
            "path",
            request.url.path,
        )
        duration = time.perf_counter() - started_at
        REQUEST_COUNT.labels(
            method=method,
            route=route,
            status="500",
        ).inc()
        REQUEST_LATENCY.labels(
            method=method,
            route=route,
        ).observe(duration)
        logging.getLogger("rootpilot.http").exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": method,
                "route": route,
                "status_code": 500,
                "duration_ms": round(
                    duration * 1000,
                    3,
                ),
            },
        )
        raise
    finally:
        REQUESTS_IN_PROGRESS.labels(
            method=method
        ).dec()

    route = getattr(
        request.scope.get("route"),
        "path",
        request.url.path,
    )
    duration = time.perf_counter() - started_at
    status_code = response.status_code
    REQUEST_COUNT.labels(
        method=method,
        route=route,
        status=str(status_code),
    ).inc()
    REQUEST_LATENCY.labels(
        method=method,
        route=route,
    ).observe(duration)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    logging.getLogger("rootpilot.http").info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": method,
            "route": route,
            "status_code": status_code,
            "duration_ms": round(duration * 1000, 3),
        },
    )

    return response


def metrics_response() -> Response:
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
