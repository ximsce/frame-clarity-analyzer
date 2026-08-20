from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from frame_clarity.cli import main, process_frames
from frame_clarity.errors import AnalysisFailureError
from frame_clarity.models import AnalyzerResult


class FakeAnalyzer:
    def __init__(self, result):
        self.result = result

    def analyze(self, path):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class CliTests(unittest.TestCase):
    def test_help_and_compatibility_invocation(self):
        completed = subprocess.run(
            [sys.executable, "identify_clearest_frames.py", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("--frames-dir", completed.stdout)

    def test_invalid_numeric_option_fails_before_analysis(self):
        completed = subprocess.run(
            [sys.executable, "identify_clearest_frames.py", "--batch-size", "0"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("must be positive", completed.stderr)

    def test_missing_directory_has_clear_nonzero_diagnostic(self):
        completed = subprocess.run(
            [sys.executable, "identify_clearest_frames.py", "--frames-dir", "does-not-exist"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not exist", completed.stderr)

    def test_invalid_filename_has_clear_nonzero_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            frames = Path(directory) / "frames"
            frames.mkdir()
            (frames / "thumbnail.png").write_bytes(b"frame")
            completed = subprocess.run(
                [sys.executable, "identify_clearest_frames.py", "--frames-dir", str(frames)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("thumbnail.png", completed.stderr)

    def test_empty_directory_has_clear_nonzero_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            frames = Path(directory) / "frames"
            frames.mkdir()
            completed = subprocess.run(
                [sys.executable, "identify_clearest_frames.py", "--frames-dir", str(frames)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("No PNG frames", completed.stderr)

    def test_failure_writes_explicit_results_and_returns_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            frames.mkdir()
            (frames / "rawFrames1.png").write_bytes(b"frame")
            with self.assertRaises(AnalysisFailureError):
                process_frames(
                    str(frames),
                    save_results=False,
                    analyzer_type="fake",
                    analyzer=FakeAnalyzer(RuntimeError("analysis broke")),
                    analyzer_model="test",
                )
            result = json.loads((root / "frame_analysis_results.json").read_text(encoding="utf-8"))
            self.assertEqual(result["frames"][0]["status"], "failed")
            self.assertIsNone(result["frames"][0]["score"])

    def test_no_save_writes_report_without_copying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            frames.mkdir()
            (frames / "rawFrames1.png").write_bytes(b"frame")
            process_frames(
                str(frames),
                save_results=False,
                analyzer_type="fake",
                analyzer=FakeAnalyzer(AnalyzerResult(80, "clear")),
                analyzer_model="test",
            )
            self.assertTrue((root / "frame_analysis_results.json").exists())
            self.assertFalse((root / "clearest_frames").exists())

    def test_main_returns_nonzero_for_failure(self):
        self.assertNotEqual(main(["--frames-dir", "missing-directory"]), 0)


if __name__ == "__main__":
    unittest.main()
