from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from frame_clarity.analyzers import calculate_clip_score, create_analyzer, parse_openai_response
from frame_clarity.core import run_analysis
from frame_clarity.discovery import discover_frames
from frame_clarity.errors import (
    AnalyzerError,
    DiscoveryError,
    ProgressError,
    ProgressMismatchError,
)
from frame_clarity.models import AnalyzerResult, FrameOutcome
from frame_clarity.progress import ProgressMetadata, ProgressStore
from frame_clarity.results import copy_top_frames, result_document, write_results


def write_frame(directory: Path, filename: str, content: bytes = b"frame") -> Path:
    path = directory / filename
    path.write_bytes(content)
    return path


class FakeAnalyzer:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def analyze(self, path: Path):
        self.calls.append(path.name)
        response = self.responses[path.name]
        if isinstance(response, Exception):
            raise response
        return response


class CoreTests(unittest.TestCase):
    def test_discovery_orders_numerically_and_hashes_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_frame(path, "rawFrames10.png")
            write_frame(path, "rawFrames2.png")
            manifest = discover_frames(path)
            self.assertEqual([item.filename for item in manifest.items], ["rawFrames2.png", "rawFrames10.png"])
            original_id = manifest.input_id
            write_frame(path, "rawFrames2.png", b"changed")
            self.assertNotEqual(original_id, discover_frames(path).input_id)

    def test_discovery_reports_invalid_empty_missing_and_duplicate_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with self.assertRaisesRegex(DiscoveryError, "thumbnail.png"):
                write_frame(path, "thumbnail.png")
                discover_frames(path)
            path.joinpath("thumbnail.png").unlink()
            with self.assertRaisesRegex(DiscoveryError, "No PNG frames"):
                discover_frames(path)
            with self.assertRaisesRegex(DiscoveryError, "does not exist"):
                discover_frames(path / "missing")
            write_frame(path, "rawFrames01.png")
            write_frame(path, "rawFrames1.png")
            with self.assertRaisesRegex(DiscoveryError, "Duplicate frame number"):
                discover_frames(path)

    def test_clip_score_and_openai_parser_are_strict(self):
        self.assertEqual(calculate_clip_score([1, 0, 1, 0, 1, 0]), 100.0)
        self.assertEqual(parse_openai_response('```json\n{"score": 72, "reasoning": "sharp"}\n```').score, 72.0)
        with self.assertRaises(AnalyzerError):
            parse_openai_response('{"reasoning": "missing score"}')
        with self.assertRaises(AnalyzerError):
            parse_openai_response('{"score": 101}')

    def test_analyzer_selection_rejects_unknown_values(self):
        with self.assertRaisesRegex(Exception, "Unknown analyzer"):
            create_analyzer("unknown")

    def test_outcomes_never_store_scores_for_failures(self):
        failed = FrameOutcome.failed("rawFrames1.png", 1, "broken", attempts=2)
        skipped = FrameOutcome.skipped("rawFrames2.png", 2, "excluded")
        self.assertIsNone(failed.score)
        self.assertIsNone(skipped.score)
        with self.assertRaises(ValueError):
            FrameOutcome("rawFrames3.png", 3, "failed", score=50, error="broken")

    def test_run_retries_failures_and_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_frame(path, "rawFrames1.png")
            write_frame(path, "rawFrames2.png")
            manifest = discover_frames(path)
            progress = ProgressStore(path / "progress.json")
            first = FakeAnalyzer({
                "rawFrames1.png": AnalyzerResult(80, "good"),
                "rawFrames2.png": RuntimeError("unreadable"),
            })
            first_run = run_analysis(
                manifest,
                first,
                analyzer_name="fake",
                model="test",
                progress_store=progress,
                batch_size=1,
            )
            self.assertFalse(first_run.successful)
            retry = FakeAnalyzer({"rawFrames2.png": AnalyzerResult(60, "recovered")})
            second_run = run_analysis(
                manifest,
                retry,
                analyzer_name="fake",
                model="test",
                progress_store=progress,
                batch_size=1,
            )
            self.assertEqual(retry.calls, ["rawFrames2.png"])
            self.assertTrue(second_run.successful)
            self.assertEqual(second_run.outcomes[1].attempts, 2)

    def test_parallel_completion_and_resume_are_deterministic(self):
        class DelayedAnalyzer(FakeAnalyzer):
            def analyze(self, path):
                time.sleep(0.01 if path.name.endswith("1.png") else 0)
                return super().analyze(path)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_frame(path, "rawFrames1.png")
            write_frame(path, "rawFrames2.png")
            manifest = discover_frames(path)
            progress = ProgressStore(path / "progress.json")
            analyzer = DelayedAnalyzer({
                "rawFrames1.png": AnalyzerResult(80, "one"),
                "rawFrames2.png": AnalyzerResult(80, "two"),
            })
            first = run_analysis(
                manifest,
                analyzer,
                analyzer_name="fake",
                model="test",
                progress_store=progress,
                max_workers=2,
            )
            self.assertEqual([outcome.filename for outcome in first.outcomes], [
                "rawFrames1.png", "rawFrames2.png"
            ])
            second_analyzer = FakeAnalyzer({})
            second = run_analysis(
                manifest,
                second_analyzer,
                analyzer_name="fake",
                model="test",
                progress_store=progress,
            )
            self.assertEqual(second_analyzer.calls, [])
            self.assertEqual(
                [outcome.to_dict() for outcome in first.outcomes],
                [outcome.to_dict() for outcome in second.outcomes],
            )

    def test_progress_round_trip_corruption_mismatch_and_legacy_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_frame(path, "rawFrames1.png")
            manifest = discover_frames(path)
            metadata = ProgressMetadata(manifest.input_id, "fake", "test")
            store = ProgressStore(path / "progress.json")
            outcome = FrameOutcome.success("rawFrames1.png", 1, 42, "ok")
            store.save(metadata, [outcome])
            self.assertEqual(store.load(manifest, metadata).outcomes[0].score, 42)
            with self.assertRaises(ProgressMismatchError):
                store.load(manifest, ProgressMetadata(manifest.input_id, "other", "test"))
            store.path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(ProgressError):
                store.load(manifest, metadata)
            store.path.write_text(json.dumps({
                "processed_frames": {"rawFrames1.png": True},
                "scores": [{"filename": "rawFrames1.png", "score": 50, "reasoning": "old"}],
            }), encoding="utf-8")
            migrated = store.load(manifest, metadata)
            self.assertTrue(migrated.migrated_legacy)
            self.assertEqual(migrated.outcomes[0].status, "success")
            self.assertEqual(json.loads(store.path.read_text(encoding="utf-8"))["version"], 1)

    def test_atomic_progress_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = ProgressStore(path / "progress.json")
            store.save(ProgressMetadata("one", "fake", "test"), [])
            original = store.path.read_text(encoding="utf-8")
            with patch("frame_clarity.storage.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(ProgressError):
                    store.save(ProgressMetadata("two", "fake", "test"), [])
            self.assertEqual(store.path.read_text(encoding="utf-8"), original)

    def test_results_rank_deterministically_and_copy_successes_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_frame(path, "rawFrames1.png", b"one")
            write_frame(path, "rawFrames2.png", b"two")
            manifest = discover_frames(path)
            outcomes = [
                FrameOutcome.success("rawFrames2.png", 2, 90),
                FrameOutcome.success("rawFrames1.png", 1, 90),
                FrameOutcome.failed("rawFrames3.png", 3, "failed"),
            ]
            document = result_document(outcomes, 2)
            self.assertEqual([frame["filename"] for frame in document["frames"]], [
                "rawFrames1.png", "rawFrames2.png", "rawFrames3.png"
            ])
            results_path = path / "results.json"
            write_results(results_path, outcomes, 2)
            output = path / "clearest"
            self.assertEqual(copy_top_frames(manifest, outcomes[:2], output, 2), 2)
            self.assertTrue((output / "001_rawFrames1.png").exists())
            self.assertTrue((output / "002_rawFrames2.png").exists())

    def test_copy_reports_missing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_frame(path, "rawFrames1.png")
            manifest = discover_frames(path)
            (path / "rawFrames1.png").unlink()
            with self.assertRaisesRegex(Exception, "Could not copy"):
                copy_top_frames(
                    manifest,
                    [FrameOutcome.success("rawFrames1.png", 1, 90)],
                    path / "output",
                    1,
                )


if __name__ == "__main__":
    unittest.main()
