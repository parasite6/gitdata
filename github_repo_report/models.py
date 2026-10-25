"""Shared report contract for CLI, tests and future GUI consumers."""
from dataclasses import dataclass
from typing import Any, Callable, TypedDict


class FieldValue(TypedDict):
    value: Any


class FieldResult(FieldValue, total=False):
    unavailable: str


# The report also carries collection and inference metadata; JSON keys remain
# compatible with the original CLI. FieldResult documents the ordinary fields.
Report = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    message: str
    retry_seconds: float | None = None
    completed: int | None = None
    total: int | None = None
    unit: str | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def is_partial(report: Report) -> bool:
    """Unavailable fields and incomplete inference make a report partial."""
    return any("unavailable" in value for value in report.values()) or bool(
                   report["supported_platforms"]["collection_errors"])
