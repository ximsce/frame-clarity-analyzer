"""Deterministic result serialization and ranked frame copying."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .errors import OutputError
from .models import FrameManifest, FrameOutcome
from .storage import atomic_write_json


def rank_outcomes(outcomes: Iterable[FrameOutcome]) -> List[FrameOutcome]:
    values = list(outcomes)
    successful = sorted(
        (outcome for outcome in values if outcome.status == "success"),
        key=lambda outcome: (-float(outcome.score), outcome.frame_index),
    )
    unresolved = sorted(
        (outcome for outcome in values if outcome.status != "success"),
        key=lambda outcome: outcome.frame_index,
    )
    return successful + unresolved


def result_document(outcomes: Iterable[FrameOutcome], top_n: int) -> Dict[str, Any]:
    ranked = rank_outcomes(outcomes)
    return {
        "total_frames": len(ranked),
        "top_n": top_n,
        "frames": [outcome.to_dict() for outcome in ranked],
    }


def write_results(path: Path, outcomes: Iterable[FrameOutcome], top_n: int) -> None:
    atomic_write_json(Path(path), result_document(outcomes, top_n), OutputError)


def copy_top_frames(
    manifest: FrameManifest,
    outcomes: Iterable[FrameOutcome],
    output_dir: Path,
    top_n: int,
) -> int:
    by_name = {item.filename: item for item in manifest.items}
    top = [outcome for outcome in rank_outcomes(outcomes) if outcome.status == "success"][:top_n]
    destination = Path(output_dir)
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for rank, outcome in enumerate(top, start=1):
            item = by_name[outcome.filename]
            target = destination / ("%03d_%s" % (rank, outcome.filename))
            shutil.copy2(str(item.path), str(target))
    except (KeyError, OSError, shutil.Error) as exc:
        raise OutputError("Could not copy frames to %s: %s" % (destination, exc)) from exc
    return len(top)
