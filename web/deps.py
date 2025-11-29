"""Database session dependency for FastAPI.

Provides a database session to route handlers via FastAPI dependency injection.

Transaction boundaries are managed here:
- Session is created at request start
- On success (no exception): session is committed automatically
- On exception: session is rolled back automatically
- Session is closed after request completes

This approach ensures consistent transaction boundaries across all endpoints
and removes the need for manual db.commit() calls in route handlers.
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

    Creates a session at the start of the request. Transaction boundaries
    are managed automatically:
    - Commits on successful completion (no exception)
    - Rolls back on any exception
    - Closes the session after request completes

    Yields:
        Database session.
    """
    session = session_factory()
    try:
        yield session
        # Commit on success - only reached if no exception was raised
        session.commit()
    except Exception:
        # Rollback on any exception
        session.rollback()
        raise
    finally:
        session.close()
