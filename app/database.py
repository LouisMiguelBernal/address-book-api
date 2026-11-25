"""Database engine, session factory and the request-scoped session dependency."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def create_db_engine(database_url: str) -> Engine:
    """Create an engine; for SQLite, enable WAL mode on every new connection."""
    is_sqlite = database_url.startswith("sqlite")
    engine = create_engine(
        database_url,
        # FastAPI runs sync endpoints in a threadpool, so a connection may be used
        # by a different thread than the one that opened it.
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            # WAL lets readers proceed while a write is in progress
            # (SQLite still allows only one writer at a time).
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False keeps loaded attributes usable after commit,
    # so a just-saved object can be serialized into the response.
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    """Yield one session per request and always close it afterwards."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
