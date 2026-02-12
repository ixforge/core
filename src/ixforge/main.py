"""FastAPI application factory."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ixforge import __version__
from ixforge.config import get_settings
from ixforge.exceptions import IXForgeError
from ixforge.logging import setup_logging
from ixforge.metrics import http_request_duration_seconds, http_requests_total


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(debug=settings.debug)
    log = structlog.get_logger()
    log.info("ixforge.startup", version=__version__, debug=settings.debug)
    yield
    log.info("ixforge.shutdown")


def create_app() -> FastAPI:
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Metrics middleware
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start
        path = request.url.path
        http_requests_total.labels(
            method=request.method, path=path, status=response.status_code
        ).inc()
        http_request_duration_seconds.labels(method=request.method, path=path).observe(duration)
        return response

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

    # Routers
    from ixforge.api.v1.router import v1_router

    app.include_router(v1_router, prefix="/api/v1")

    # Prometheus metrics endpoint
    from ixforge.api.v1.metrics import metrics_router

    app.include_router(metrics_router)

    return app


app = create_app()
