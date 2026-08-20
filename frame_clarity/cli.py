"""Command-line adapter for the reusable frame analysis core."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from .analyzers import AnalyzerProtocol, create_analyzer
from .core import run_analysis
from .discovery import discover_frames
from .errors import AnalysisFailureError, ConfigurationError, FrameClarityError
from .models import FrameOutcome, RunResult
from .progress import ProgressStore
from .results import copy_top_frames, result_document, write_results


VERSION = "0.1.0"


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def _validate_destination(path: Path, label: str) -> None:
    if path.exists() and path.is_dir():
        raise ConfigurationError("%s path is a directory: %s" % (label, path))
    parent = path.parent
    if parent.exists() and not parent.is_dir():
        raise ConfigurationError("%s parent is not a directory: %s" % (label, parent))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Identify clearest frames from video frames using AI")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument(
        "--frames-dir",
        default="dancingFrames",
        help="Directory containing frame images (default: dancingFrames)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to save clearest frames (default: clearest_frames in parent dir)",
    )
    parser.add_argument(
        "--progress-file",
        default=None,
        help="Progress JSON path (default: frame_analysis_progress.json beside frames)",
    )
    parser.add_argument(
        "--results-file",
        default=None,
        help="Results JSON path (default: frame_analysis_results.json beside frames)",
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=10,
        help="Number of frames to process per batch (default: 10)",
    )
    parser.add_argument(
        "--top-n",
        type=_positive_int,
        default=50,
        help="Number of top clearest frames to save (default: 50)",
    )
    parser.add_argument("--api-key", default=None, help="OpenAI API key (or set OPENAI_API_KEY)")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model to use (default: gpt-4o)")
    parser.add_argument(
        "--max-workers",
        type=_positive_int,
        default=1,
        help="Maximum parallel API calls per batch (default: 1)",
    )
    parser.add_argument("--no-save", action="store_true", help="Do not copy frames; only generate JSON")
    parser.add_argument(
        "--free-tier",
        action="store_true",
        default=True,
        help="Enable free tier optimizations (default: True)",
    )
    parser.add_argument(
        "--no-free-tier",
        action="store_false",
        dest="free_tier",
        help="Disable free tier optimizations (for paid accounts)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Do not resume from previous progress",
    )
    parser.add_argument(
        "--analyzer",
        choices=["clip", "openai"],
        default="clip",
        help="Analyzer to use: clip or openai (default: clip)",
    )
    parser.add_argument(
        "--clip-model",
        default="openai/clip-vit-base-patch32",
        help="CLIP model to use (default: openai/clip-vit-base-patch32)",
    )
    parser.add_argument(
        "--requests-per-minute",
        type=_positive_int,
        default=3,
        help="OpenAI request limit (default: 3)",
    )
    parser.add_argument(
        "--delay-between-requests",
        type=_nonnegative_float,
        default=20.0,
        help="Minimum OpenAI request delay in seconds (default: 20.0)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Console output format (default: text)",
    )
    return parser


def process_frames(
    frames_dir: str,
    output_dir: Optional[str] = None,
    batch_size: int = 5,
    top_n: int = 50,
    api_key: Optional[str] = None,
    model: str = "gpt-4o",
    max_workers: int = 1,
    save_results: bool = True,
    free_tier: bool = True,
    requests_per_minute: int = 3,
    delay_between_requests: float = 20.0,
    resume: bool = True,
    analyzer_type: str = "clip",
    clip_model: str = "openai/clip-vit-base-patch32",
    progress_file: Optional[str] = None,
    results_file: Optional[str] = None,
    analyzer: Optional[AnalyzerProtocol] = None,
    analyzer_model: Optional[str] = None,
    output_format: str = "text",
) -> List[FrameOutcome]:
    """Preserve the original callable entry point while using the core layers."""

    manifest = discover_frames(Path(frames_dir))
    parent = manifest.directory.parent
    progress_path = Path(progress_file) if progress_file else parent / "frame_analysis_progress.json"
    results_path = Path(results_file) if results_file else parent / "frame_analysis_results.json"
    _validate_destination(progress_path, "Progress file")
    _validate_destination(results_path, "Results file")
    if output_dir is not None:
        output_path = Path(output_dir)
        if output_path.exists() and not output_path.is_dir():
            raise ConfigurationError("Output path is not a directory: %s" % output_path)

    selected_workers = max_workers
    selected_model = analyzer_model or (clip_model if analyzer_type == "clip" else model)
    if analyzer is None:
        if analyzer_type == "openai" and free_tier:
            selected_workers = 1
        analyzer, selected_model = create_analyzer(
            analyzer_type,
            api_key=api_key,
            model=model,
            clip_model=clip_model,
            requests_per_minute=requests_per_minute,
            delay_between_requests=delay_between_requests,
        )

    run = run_analysis(
        manifest,
        analyzer,
        analyzer_name=analyzer_type,
        model=selected_model,
        progress_store=ProgressStore(progress_path),
        resume=resume,
        batch_size=batch_size,
        max_workers=selected_workers,
        secrets=[api_key or os.getenv("OPENAI_API_KEY", "")],
        top_n=top_n,
    )
    write_results(results_path, run.outcomes, top_n)
    copied = 0
    if save_results:
        destination = Path(output_dir) if output_dir else parent / "clearest_frames"
        copied = copy_top_frames(manifest, run.outcomes, destination, top_n)

    if output_format == "json":
        print(json.dumps(result_document(run.outcomes, top_n), indent=2, sort_keys=True))
    else:
        print("Found %s frames" % len(manifest.items))
        print("Saved results to %s" % results_path)
        print("Copied %s successful top frame(s)" % copied)
        failures = [outcome for outcome in run.outcomes if outcome.status == "failed"]
        if failures:
            for outcome in failures:
                print("Failed %s: %s" % (outcome.filename, outcome.error), file=sys.stderr)

    if not run.successful:
        failed = [outcome.filename for outcome in run.outcomes if outcome.status == "failed"]
        raise AnalysisFailureError("Analysis failed for: %s" % ", ".join(failed))
    return run.outcomes


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        process_frames(
            frames_dir=args.frames_dir,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            top_n=args.top_n,
            api_key=args.api_key,
            model=args.model,
            max_workers=args.max_workers,
            save_results=not args.no_save,
            free_tier=args.free_tier,
            requests_per_minute=args.requests_per_minute,
            delay_between_requests=args.delay_between_requests,
            resume=args.resume,
            analyzer_type=args.analyzer,
            clip_model=args.clip_model,
            progress_file=args.progress_file,
            results_file=args.results_file,
            output_format=args.format,
        )
        return 0
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)
        return 130
    except FrameClarityError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
