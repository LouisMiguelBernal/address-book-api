"""Application entry point.

Run with:  uvicorn app.main:app --reload
"""

import logging
import re
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

# A client-supplied request ID is reused only if it is short and plain; anything
# else (newlines, huge values) could forge or flood log lines, so a new ID is generated.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


def _request_id_from(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "")
    return supplied if _VALID_REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex[:12]


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
        """Tag the request with an ID; log method, path, status and duration.

        Also the last line of defence: an unexpected exception is logged once with
        its traceback and turned into a JSON 500 that still carries the request ID.
        """
        request_id = _request_id_from(request)
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("Unhandled error on %s %s", request.method, request.url.path)
                response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
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
        finally:
            request_id_var.reset(token)

    @app.exception_handler(RequestValidationError)
    async def log_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Log which fields were rejected, then return FastAPI's standard 422 response.

        Only field locations and error types are logged, never the submitted
        values: addresses are personal data and must not end up in log files.
        """
        problems = [f"{'.'.join(str(part) for part in err['loc'])}: {err['type']}" for err in exc.errors()]
        logger.warning(
            "Validation failed on %s %s: %s", request.method, request.url.path, "; ".join(problems)
        )
        return await request_validation_exception_handler(request, exc)

    app.include_router(addresses.router)
    return app


app = create_app()
