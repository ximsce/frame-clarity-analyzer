"""Versioned, atomic progress persistence and legacy migration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .errors import ProgressError, ProgressMismatchError
from .models import FrameManifest, FrameOutcome, SCORING_VERSION
from .storage import atomic_write_json, read_json


PROGRESS_VERSION = 1


@dataclass(frozen=True)
class ProgressMetadata:
    input_id: str
    analyzer: str
    model: str
    scoring_version: str = SCORING_VERSION

    def to_dict(self) -> Dict[str, str]:
        return {
            "input_id": self.input_id,
            "analyzer": self.analyzer,
            "model": self.model,
            "scoring_version": self.scoring_version,
        }


@dataclass
class ProgressState:
    metadata: ProgressMetadata
    outcomes: List[FrameOutcome]
    migrated_legacy: bool = False


class ProgressStore:
    """Read and write progress for one destination path."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def save(self, metadata: ProgressMetadata, outcomes: Iterable[FrameOutcome]) -> None:
        ordered = sorted(outcomes, key=lambda outcome: outcome.frame_index)
        payload = {
            "version": PROGRESS_VERSION,
            "metadata": metadata.to_dict(),
            "frames": [outcome.to_dict() for outcome in ordered],
        }
        atomic_write_json(self.path, payload, ProgressError)

    def load(self, manifest: FrameManifest, metadata: ProgressMetadata) -> Optional[ProgressState]:
        if not self.path.exists():
            return None
        payload = read_json(self.path, ProgressError)
        if not isinstance(payload, dict):
            raise ProgressError("Progress file must contain a JSON object: %s" % self.path)
        if "processed_frames" in payload or "scores" in payload:
            state = self._load_legacy(payload, manifest, metadata)
            self.save(state.metadata, state.outcomes)
            return state

        if payload.get("version") != PROGRESS_VERSION:
            raise ProgressError("Unsupported progress version in %s" % self.path)
        raw_metadata = payload.get("metadata")
        if not isinstance(raw_metadata, dict):
            raise ProgressError("Progress metadata is missing or invalid: %s" % self.path)
        expected = metadata.to_dict()
        if raw_metadata != expected:
            differences = [
                key for key in expected if raw_metadata.get(key) != expected.get(key)
            ]
            raise ProgressMismatchError(
                "Progress metadata mismatch in %s: %s"
                % (self.path, ", ".join(differences) or "unknown metadata")
            )

        raw_frames = payload.get("frames")
        if not isinstance(raw_frames, list):
            raise ProgressError("Progress frames must be a list: %s" % self.path)
        outcomes = self._parse_outcomes(raw_frames, manifest)
        return ProgressState(metadata=metadata, outcomes=outcomes)

    def _parse_outcomes(
        self, raw_frames: List[Any], manifest: FrameManifest
    ) -> List[FrameOutcome]:
        by_name = {item.filename: item for item in manifest.items}
        seen = set()
        outcomes: List[FrameOutcome] = []
        for value in raw_frames:
            try:
                outcome = FrameOutcome.from_dict(value)
            except (TypeError, ValueError, KeyError) as exc:
                raise ProgressError("Invalid frame outcome in %s: %s" % (self.path, exc)) from exc
            if outcome.filename in seen:
                raise ProgressError("Duplicate frame in progress: %s" % outcome.filename)
            item = by_name.get(outcome.filename)
            if item is None or item.frame_index != outcome.frame_index:
                raise ProgressError(
                    "Progress frame does not match the current input set: %s" % outcome.filename
                )
            seen.add(outcome.filename)
            outcomes.append(outcome)
        return sorted(outcomes, key=lambda outcome: outcome.frame_index)

    def _load_legacy(
        self,
        payload: Dict[str, Any],
        manifest: FrameManifest,
        metadata: ProgressMetadata,
    ) -> ProgressState:
        processed = payload.get("processed_frames")
        scores = payload.get("scores")
        if not isinstance(processed, dict) or not isinstance(scores, list):
            raise ProgressError("Legacy progress must contain processed_frames and scores")
        by_name = {item.filename: item for item in manifest.items}
        score_by_name: Dict[str, Any] = {}
        for value in scores:
            if not isinstance(value, dict) or "filename" not in value or "score" not in value:
                raise ProgressError("Legacy progress contains an invalid score entry")
            filename = value["filename"]
            if filename not in by_name:
                raise ProgressError("Legacy progress contains an unknown frame: %s" % filename)
            if filename in score_by_name:
                raise ProgressError("Legacy progress contains duplicate frame: %s" % filename)
            score_by_name[filename] = value["score"]

        outcomes: List[FrameOutcome] = []
        for filename, marked in processed.items():
            if marked is not True or filename not in by_name or filename not in score_by_name:
                raise ProgressError("Legacy progress contains an ambiguous frame: %s" % filename)
            score = score_by_name[filename]
            try:
                numeric_score = float(score)
            except (TypeError, ValueError) as exc:
                raise ProgressError("Legacy score is invalid for %s" % filename) from exc
            if not math.isfinite(numeric_score) or not 0 <= numeric_score <= 100:
                raise ProgressError("Legacy score is outside 0-100 for %s" % filename)
            item = by_name[filename]
            outcomes.append(
                FrameOutcome.success(
                    filename=filename,
                    frame_index=item.frame_index,
                    score=numeric_score,
                    reasoning=str(next(
                        value.get("reasoning", "")
                        for value in scores
                        if value.get("filename") == filename
                    )),
                    attempts=1,
                )
            )
        return ProgressState(metadata=metadata, outcomes=outcomes, migrated_legacy=True)
