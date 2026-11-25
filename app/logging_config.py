"""Logging setup.

Every log line carries a request ID so all lines produced by one HTTP request
can be grouped together. The ID lives in a ContextVar, which is safe both for
async handlers and for sync handlers that FastAPI runs in its threadpool.
"""

import logging
import logging.config
from contextvars import ContextVar

# "-" marks log lines emitted outside a request (startup, shutdown).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger and align uvicorn's loggers with it."""
    logging.config.dictConfig(
        {
            "version": 1,
            # Keep loggers created at import time (e.g. by uvicorn) working.
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                },
            },
            "root": {"level": level.upper(), "handlers": ["console"]},
            "loggers": {
                # Route uvicorn's server messages through our format.
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                # Requests are logged by our middleware; silence the duplicate access log.
                "uvicorn.access": {"handlers": [], "propagate": False, "level": "WARNING"},
            },
        }
    )
