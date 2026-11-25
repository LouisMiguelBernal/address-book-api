"""Application entry point.

Run with:  uvicorn app.main:app --reload
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings, get_settings
from app.database import Base, create_db_engine, create_session_factory
from app.logging_config import request_id_var, setup_logging
from app.routers import addresses

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Tests pass their own settings (e.g. a temporary database)."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # create_all only creates missing tables; existing data is kept.
        Base.metadata.create_all(engine)
        logger.info("Database ready at %s", settings.database_url)
        yield
        engine.dispose()
        logger.info("Database connections closed")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Create, update and delete addresses, and find addresses within a distance of a point.",
        lifespan=lifespan,
    )
    app.state.session_factory = create_session_factory(engine)

    @app.middleware("http")
    async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Tag the request with an ID and log method, path, status and duration."""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s -> %d (%.1f ms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            # Returned to the client so a request can be matched to its log lines.
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            raise
        finally:
            request_id_var.reset(token)

    @app.exception_handler(RequestValidationError)
    async def log_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Log rejected input, then return FastAPI's standard 422 response."""
        logger.warning("Validation failed on %s %s: %s", request.method, request.url.path, exc.errors())
        return await request_validation_exception_handler(request, exc)

    app.include_router(addresses.router)
    return app


app = create_app()
