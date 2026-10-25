"""Reusable GitHub reporting core. Only the CLI writes to the terminal."""
from .api import API
from .errors import APIError, Cancelled, RateLimited, Unavailable
from .inputs import repository
from .models import FieldResult, ProgressCallback, ProgressEvent, Report, is_partial
from .report import build_report

__all__ = [
    "API", "APIError", "Cancelled", "RateLimited", "Unavailable", "FieldResult",
    "ProgressCallback", "ProgressEvent", "Report", "build_report",
    "is_partial", "repository",
]
