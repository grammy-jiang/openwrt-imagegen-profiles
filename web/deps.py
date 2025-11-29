"""Database session dependency for FastAPI.

Provides a database session to route handlers via FastAPI dependency injection.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Get session factory from app state.

    Args:
        request: FastAPI request object.

    Returns:
        SQLAlchemy session factory.
    """
    factory: Any = request.app.state.session_factory
    return factory  # type: ignore[no-any-return]


def get_db(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> Generator[Session, None, None]:
    """Provide a database session for a request.

    Creates a session at the start of the request and closes it
    when the request completes.

    Yields:
        Database session.
    """
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
