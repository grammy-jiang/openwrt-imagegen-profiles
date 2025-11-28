"""Database engine and session management for openwrt_imagegen.

This module provides SQLAlchemy engine creation, session factory,
and base model class for all ORM models.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from openwrt_imagegen.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


def get_engine(db_url: str | None = None) -> Any:
    """Create and return a SQLAlchemy engine.

    Args:
        db_url: Database URL. If not provided, uses settings default.

    Returns:
        SQLAlchemy Engine instance.
    """
    if db_url is None:
        settings = get_settings()
        db_url = settings.db_url

    # SQLite-specific connect args for better concurrency
    connect_args: dict[str, Any] = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        db_url,
        connect_args=connect_args,
        echo=False,
    )


def get_session_factory(engine: Any | None = None) -> sessionmaker[Session]:
    """Create and return a session factory.

    Args:
        engine: SQLAlchemy engine. If not provided, creates one from settings.

    Returns:
        Session factory (sessionmaker).
    """
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def get_session(
    session_factory: sessionmaker[Session] | None = None,
) -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.

    Args:
        session_factory: Optional session factory. Creates one if not provided.

    Yields:
        SQLAlchemy Session instance.
    """
    if session_factory is None:
        session_factory = get_session_factory()

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all_tables(engine: Any | None = None) -> None:
    """Create all tables defined by ORM models.

    This is primarily for testing and development. Production deployments
    should use Alembic migrations.

    Args:
        engine: SQLAlchemy engine. If not provided, creates one from settings.
    """
    # Import all models to ensure they are registered with SQLAlchemy's mapper
    # before creating tables. This resolves relationship references.
    from openwrt_imagegen.builds import models as builds_models  # noqa: F401
    from openwrt_imagegen.flash import models as flash_models  # noqa: F401
    from openwrt_imagegen.imagebuilder import (
        models as imagebuilder_models,  # noqa: F401
    )
    from openwrt_imagegen.profiles import models as profiles_models  # noqa: F401

    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(bind=engine)


def drop_all_tables(engine: Any | None = None) -> None:
    """Drop all tables defined by ORM models.

    WARNING: This is destructive. Only use in testing.

    Args:
        engine: SQLAlchemy engine. If not provided, creates one from settings.
    """
    if engine is None:
        engine = get_engine()
    Base.metadata.drop_all(bind=engine)


__all__ = [
    "Base",
    "create_all_tables",
    "drop_all_tables",
    "get_engine",
    "get_session",
    "get_session_factory",
]
