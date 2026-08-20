"""Dependency-free data contracts used by the analysis workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCORING_VERSION = "1"
STATUSES = {"success", "failed", "skipped"}


@dataclass(frozen=True)
class FrameManifestItem:
    """A validated frame and the identity data used for resume checks."""

    filename: str
    path: Path
    frame_index: int
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class FrameManifest:
    """The ordered, immutable input set for one run."""

    directory: Path
    prefix: str
    items: Tuple[FrameManifestItem, ...]
    input_id: str


@dataclass(frozen=True)
class AnalyzerResult:
    """A candidate result returned by an analyzer before orchestration."""

    score: float
    reasoning: str = ""


@dataclass
class FrameOutcome:
    """Persisted state for one frame."""

    filename: str
    frame_index: int
    status: str
    score: Optional[float] = None
    reasoning: str = ""
    error: Optional[str] = None
    attempts: int = 0

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError("Unknown frame status: %s" % self.status)
        if self.attempts < 0:
            raise ValueError("Frame attempts cannot be negative")
        if self.status == "success":
            if self.score is None or not isfinite(float(self.score)):
                raise ValueError("Successful frames require a finite score")
            if not 0 <= float(self.score) <= 100:
                raise ValueError("Frame scores must be between 0 and 100")
            self.score = float(self.score)
            self.error = None
        elif self.status == "failed":
            if not self.error:
                raise ValueError("Failed frames require an error")
            if self.score is not None:
                raise ValueError("Failed frames cannot have a score")
            self.score = None
        else:
            if not self.error:
                raise ValueError("Skipped frames require a reason")
            if self.score is not None:
                raise ValueError("Skipped frames cannot have a score")
            self.score = None

    @classmethod
    def success(
        cls,
        filename: str,
        frame_index: int,
        score: float,
        reasoning: str = "",
        attempts: int = 1,
    ) -> "FrameOutcome":
        return cls(filename, frame_index, "success", score, reasoning, None, attempts)

    @classmethod
    def failed(
        cls,
        filename: str,
        frame_index: int,
        error: str,
        attempts: int = 1,
    ) -> "FrameOutcome":
        return cls(filename, frame_index, "failed", None, "", error, attempts)

    @classmethod
    def skipped(
        cls,
        filename: str,
        frame_index: int,
        reason: str,
        attempts: int = 0,
    ) -> "FrameOutcome":
        return cls(filename, frame_index, "skipped", None, "", reason, attempts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "frame_index": self.frame_index,
            "status": self.status,
            "score": self.score,
            "reasoning": self.reasoning,
            "error": self.error,
            "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "FrameOutcome":
        if not isinstance(value, dict):
            raise ValueError("Frame outcome must be an object")
        required = {"filename", "frame_index", "status", "attempts"}
        missing = required.difference(value)
        if missing:
            raise ValueError("Frame outcome is missing: %s" % ", ".join(sorted(missing)))
        return cls(
            filename=str(value["filename"]),
            frame_index=int(value["frame_index"]),
            status=str(value["status"]),
            score=value.get("score"),
            reasoning=str(value.get("reasoning") or ""),
            error=value.get("error"),
            attempts=int(value["attempts"]),
        )


@dataclass
class RunResult:
    """The result of one orchestrated run."""

    outcomes: List[FrameOutcome] = field(default_factory=list)
    top_n: int = 50

    @property
    def successful(self) -> bool:
        return all(outcome.status in {"success", "skipped"} for outcome in self.outcomes)
