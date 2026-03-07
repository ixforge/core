"""FastAPI application factory."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ixforge import __version__
from ixforge.config import get_settings
from ixforge.exceptions import IXForgeError
from ixforge.logging import setup_logging
from ixforge.metrics import http_request_duration_seconds, http_requests_total


class RequestIDMiddleware:
    """Pure ASGI middleware that injects a request ID into structlog context."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Reset tenant context for this request
        from ixforge.database import tenant_context

        tenant_token = tenant_context.set(None)

        try:
            headers = dict(scope.get("headers", []))
            request_id = headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())

            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(request_id=request_id)

            async def send_with_request_id(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", request_id.encode()))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_request_id)
        finally:
            tenant_context.reset(tenant_token)


class MetricsMiddleware:
    """Pure ASGI middleware that records request duration and count."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_with_metrics(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_metrics)
        finally:
            duration = time.perf_counter() - start
            # Use normalized route template to avoid unbounded cardinality
            route = scope.get("route")
            path = route.path if route and hasattr(route, "path") else scope.get("path", "unknown")
            method = scope.get("method", "")
            http_requests_total.labels(method=method, path=path, status=status_code).inc()
            http_request_duration_seconds.labels(method=method, path=path).observe(duration)


class SecurityHeadersMiddleware:
    """Pure ASGI middleware that adds security headers to all HTTP responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                ])
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(debug=settings.debug)
    log = structlog.get_logger()
    log.info("ixforge.startup", version=__version__, debug=settings.debug)
    yield
    log.info("ixforge.shutdown")
    from ixforge.database import dispose_engine

    await dispose_engine()


def create_app(*, enable_rate_limit: bool = True) -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="IXForge",
        description="Modular IXP management platform",
        version=__version__,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Rate limiting (SlowAPIMiddleware uses BaseHTTPMiddleware internally,
    # which breaks asyncpg in tests; disable via enable_rate_limit=False)
    if enable_rate_limit:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware

        from ixforge.rate_limit import limiter

        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # Pure ASGI middlewares (no BaseHTTPMiddleware, safe with asyncpg)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # Exception handlers
    @app.exception_handler(IXForgeError)
    async def ixforge_error_handler(request: Request, exc: IXForgeError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log = structlog.get_logger()
        log.error(
            "unhandled_exception",
            exc_type=type(exc).__name__,
            exc_message=str(exc),
            path=request.url.path,
            method=request.method,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "details": {},
                }
            },
        )

    # Routers
    from ixforge.api.v1.router import v1_router

    app.include_router(v1_router, prefix="/api/v1")

    # Prometheus metrics endpoint
    from ixforge.api.v1.metrics import metrics_router

    app.include_router(metrics_router)

    return app


app = create_app()
