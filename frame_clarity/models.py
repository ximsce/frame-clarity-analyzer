"""Dependency-free data contracts used by the analysis workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCORING_VERSION = "1"
STATUSES = {"success", "failed", "skipped"}


@dataclass(frozen=True)
class FrameProvenance:
    """Source and extraction context for a frame originating in a video."""

    source_id: str
    source_name: str
    stream_index: int
    requested_timestamp_seconds: float
    actual_timestamp_seconds: Optional[float] = None
    sampling_fps: float = 30.0
    extraction_id: str = ""
    extractor: str = "ffmpeg"
    extractor_version: str = ""
    stream: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_name:
            raise ValueError("Frame provenance requires a source identity and name")
        if self.stream_index < 0:
            raise ValueError("Frame provenance stream index cannot be negative")
        if not isfinite(float(self.requested_timestamp_seconds)) or self.requested_timestamp_seconds < 0:
            raise ValueError("Frame provenance requires a nonnegative timestamp")
        if self.actual_timestamp_seconds is not None:
            if not isfinite(float(self.actual_timestamp_seconds)) or self.actual_timestamp_seconds < 0:
                raise ValueError("Actual frame timestamp must be nonnegative")
        if not isfinite(float(self.sampling_fps)) or self.sampling_fps <= 0:
            raise ValueError("Frame provenance sampling rate must be positive")

    def to_dict(self) -> Dict[str, Any]:
        timestamp = (
            self.actual_timestamp_seconds
            if self.actual_timestamp_seconds is not None
            else self.requested_timestamp_seconds
        )
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "stream_index": self.stream_index,
            "stream": dict(self.stream),
            "timestamp_seconds": timestamp,
            "requested_timestamp_seconds": self.requested_timestamp_seconds,
            "actual_timestamp_seconds": self.actual_timestamp_seconds,
            "sampling_fps": self.sampling_fps,
            "extraction_id": self.extraction_id,
            "extractor": self.extractor,
            "extractor_version": self.extractor_version,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "FrameProvenance":
        if not isinstance(value, dict):
            raise ValueError("Frame provenance must be an object")
        required = {"source_id", "source_name", "stream_index"}
        missing = required.difference(value)
        if missing:
            raise ValueError("Frame provenance is missing: %s" % ", ".join(sorted(missing)))
        requested = value.get("requested_timestamp_seconds", value.get("timestamp_seconds"))
        if requested is None:
            raise ValueError("Frame provenance is missing a timestamp")
        stream = value.get("stream", {})
        if not isinstance(stream, dict):
            raise ValueError("Frame provenance stream must be an object")
        return cls(
            source_id=str(value["source_id"]),
            source_name=str(value["source_name"]),
            stream_index=int(value["stream_index"]),
            requested_timestamp_seconds=float(requested),
            actual_timestamp_seconds=(
                float(value["actual_timestamp_seconds"])
                if value.get("actual_timestamp_seconds") is not None
                else None
            ),
            sampling_fps=float(value.get("sampling_fps", 30.0)),
            extraction_id=str(value.get("extraction_id") or ""),
            extractor=str(value.get("extractor") or "ffmpeg"),
            extractor_version=str(value.get("extractor_version") or ""),
            stream=dict(stream),
        )


@dataclass(frozen=True)
class FrameManifestItem:
    """A validated frame and the identity data used for resume checks."""

    filename: str
    path: Path
    frame_index: int
    size: int
    mtime_ns: int
    sha256: str
    provenance: Optional[FrameProvenance] = None


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
    provenance: Optional[FrameProvenance] = None

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
        provenance: Optional[FrameProvenance] = None,
    ) -> "FrameOutcome":
        return cls(filename, frame_index, "success", score, reasoning, None, attempts, provenance)

    @classmethod
    def failed(
        cls,
        filename: str,
        frame_index: int,
        error: str,
        attempts: int = 1,
        provenance: Optional[FrameProvenance] = None,
    ) -> "FrameOutcome":
        return cls(filename, frame_index, "failed", None, "", error, attempts, provenance)

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
        value = {
            "filename": self.filename,
            "frame_index": self.frame_index,
            "status": self.status,
            "score": self.score,
            "reasoning": self.reasoning,
            "error": self.error,
            "attempts": self.attempts,
        }
        if self.provenance is not None:
            value["provenance"] = self.provenance.to_dict()
        return value

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
            provenance=(
                FrameProvenance.from_dict(value["provenance"])
                if value.get("provenance") is not None
                else None
            ),
        )


@dataclass
class RunResult:
    """The result of one orchestrated run."""

    outcomes: List[FrameOutcome] = field(default_factory=list)
    top_n: int = 50

    @property
    def successful(self) -> bool:
        return all(outcome.status in {"success", "skipped"} for outcome in self.outcomes)
