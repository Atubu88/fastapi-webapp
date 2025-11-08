"""Backward compatibility shim for legacy imports."""
from __future__ import annotations

from webapp.db.models import *  # noqa: F401,F403
from webapp.db.models import __all__ as _models_all

__all__ = list(_models_all)
