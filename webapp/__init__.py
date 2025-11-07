"""Quiz FastAPI web application package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - used only for type checking.
    from .main import app as _app, app

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    """Lazily import the FastAPI application instance on demand.

    Importing :mod:`webapp` should not eagerly import :mod:`webapp.main` because
    Alembic's migration environment needs to import ``webapp.models`` without
    triggering application startup, which requires runtime configuration (e.g.
    ``DATABASE_URL``).  ``__getattr__`` defers the import until the ``app``
    attribute is accessed, preserving the public API while avoiding side
    effects during migrations.
    """

    if name == "app":
        from .main import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")