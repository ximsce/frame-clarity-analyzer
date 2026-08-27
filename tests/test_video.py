from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from frame_clarity.cli import process_video
from frame_clarity.cli import build_parser, main
from frame_clarity.core import run_analysis
from frame_clarity.discovery import discover_frames
from frame_clarity.errors import ExtractionError, ProgressMismatchError, VideoInputError
from frame_clarity.models import AnalyzerResult
from frame_clarity.progress import ProgressMetadata, ProgressStore
from frame_clarity.video import (
    FFmpegRunner,
    MediaCommandResult,
    VideoProbe,
    extract_video,
)


class FakeAnalyzer:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def analyze(self, path):
        self.calls.append(path.name)
        return self.result


class FakeMediaRunner:
    identity = "fake-ffmpeg"
    version = "test"

    def __init__(self, duration=1.0, failure=None):
        self.duration = duration
        self.failure = failure
        self.extract_calls = 0

    def probe(self, path: Path) -> VideoProbe:
        return VideoProbe(
            path=Path(path).resolve(),
            source_id="source-id",
            source_name=Path(path).name,
            duration_seconds=self.duration,
            stream_index=0,
            stream={"codec_name": "h264", "width": 2, "height": 2},
        )

    def extract(self, probe, output_dir, prefix, sample_fps, expected_frames):
        self.extract_calls += 1
        if self.failure is not None:
            raise self.failure
        for index in range(1, expected_frames + 1):
            Image.new("RGB", (2, 2), color=(index % 255, 0, 0)).save(
                Path(output_dir) / ("%s%06d.png" % (prefix, index))
            )


class VideoTests(unittest.TestCase):
    def test_ffmpeg_runner_builds_safe_probe_and_extract_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mov"
            source.write_bytes(b"video")
            commands = []

            def run(argv, timeout):
                commands.append(list(argv))
                if "ffprobe" in argv[0]:
                    return MediaCommandResult(
                        0,
                        json.dumps({
                            "format": {"duration": "1.0"},
                            "streams": [{
                                "index": 0,
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 2,
                                "height": 2,
                                "disposition": {"attached_pic": 0},
                            }],
                        }),
                    )
                return MediaCommandResult(0)

            runner = FFmpegRunner(ffmpeg="ffmpeg", ffprobe="ffprobe", run_fn=run)
            probe = runner.probe(source)
            runner.extract(probe, root / "frames", "rawFrames", 30.0, 30)

            self.assertEqual(probe.stream_index, 0)
            command = commands[1]
            self.assertLess(command.index("-autorotate"), command.index("-i"))
            self.assertIn("-map", command)
            self.assertIn("0:0", command)
            self.assertIn("fps=30,format=rgb24", command)
            self.assertNotIn("shell=True", command)

    def test_ffmpeg_runner_reports_missing_tools_and_bad_probe_output(self):
        with self.assertRaisesRegex(VideoInputError, "ffmpeg executable"):
            FFmpegRunner(ffmpeg="missing-ffmpeg", ffprobe="ffprobe")

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip.mov"
            source.write_bytes(b"video")

            def malformed_run(argv, timeout):
                return MediaCommandResult(0, "not-json")

            with self.assertRaisesRegex(VideoInputError, "invalid JSON"):
                FFmpegRunner(run_fn=malformed_run).probe(source)

            def no_video_run(argv, timeout):
                return MediaCommandResult(
                    0,
                    json.dumps({
                        "format": {"duration": "1"},
                        "streams": [{"index": 0, "codec_type": "audio"}],
                    }),
                )

            with self.assertRaisesRegex(VideoInputError, "usable video stream"):
                FFmpegRunner(run_fn=no_video_run).probe(source)

    def test_ffmpeg_runner_translates_timeout_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip.mov"
            source.write_bytes(b"video")

            def timeout_run(argv, timeout):
                raise subprocess.TimeoutExpired(argv, timeout)

            with self.assertRaisesRegex(ExtractionError, "Could not run ffprobe"):
                FFmpegRunner(run_fn=timeout_run).probe(source)

            def failed_run(argv, timeout):
                return MediaCommandResult(1, "", "decoder failed")

            with self.assertRaisesRegex(ExtractionError, "decoder failed"):
                FFmpegRunner(run_fn=failed_run).probe(source)

    def test_duration_limit_is_checked_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "long.mp4"
            source.write_bytes(b"video")
            runner = FakeMediaRunner(duration=180.1)
            with self.assertRaisesRegex(VideoInputError, "180-second"):
                extract_video(source, runner=runner)
            self.assertEqual(runner.extract_calls, 0)

    def test_extracts_provenance_and_reuses_complete_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            extraction_dir = root / "frames"
            runner = FakeMediaRunner()
            first = extract_video(source, extraction_dir=extraction_dir, runner=runner)
            second = extract_video(source, extraction_dir=extraction_dir, runner=runner)

            self.assertEqual(runner.extract_calls, 1)
            self.assertEqual(first.extraction_id, second.extraction_id)
            self.assertEqual(second.frame_count, 30)
            self.assertEqual(
                second.provenance_by_filename["rawFrames000001.png"].requested_timestamp_seconds,
                0.0,
            )
            self.assertTrue((extraction_dir / "video_extraction_manifest.json").exists())

    def test_changed_sampling_configuration_rebuilds_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            extraction_dir = root / "frames"
            runner = FakeMediaRunner()
            extract_video(source, extraction_dir=extraction_dir, runner=runner)
            rebuilt = extract_video(
                source,
                extraction_dir=extraction_dir,
                sample_fps=15.0,
                runner=runner,
            )

            self.assertEqual(runner.extract_calls, 2)
            self.assertEqual(rebuilt.frame_count, 15)

    def test_provenance_survives_analysis_progress_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            extraction = extract_video(
                source,
                extraction_dir=root / "frames",
                sample_fps=1.0,
                runner=FakeMediaRunner(duration=1.0),
            )
            manifest = discover_frames(
                extraction.frames_dir,
                prefix=extraction.prefix,
                provenance_by_filename=extraction.provenance_by_filename,
                identity_context=extraction.extraction_id,
            )
            progress = ProgressStore(root / "progress.json")
            first = run_analysis(
                manifest,
                FakeAnalyzer(AnalyzerResult(80, "clear")),
                analyzer_name="fake",
                model="test",
                progress_store=progress,
            )
            second_analyzer = FakeAnalyzer(AnalyzerResult(0, "unused"))
            second = run_analysis(
                manifest,
                second_analyzer,
                analyzer_name="fake",
                model="test",
                progress_store=progress,
            )

            self.assertEqual(second_analyzer.calls, [])
            self.assertEqual(
                first.outcomes[0].provenance.to_dict(),
                second.outcomes[0].provenance.to_dict(),
            )

    def test_changed_extraction_context_is_rejected_by_analysis_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            extraction_dir = root / "frames"
            runner = FakeMediaRunner(duration=1.0)
            first_extraction = extract_video(
                source,
                extraction_dir=extraction_dir,
                sample_fps=1.0,
                runner=runner,
            )
            first_manifest = discover_frames(
                first_extraction.frames_dir,
                prefix=first_extraction.prefix,
                provenance_by_filename=first_extraction.provenance_by_filename,
                identity_context=first_extraction.extraction_id,
            )
            progress = ProgressStore(root / "progress.json")
            progress.save(ProgressMetadata(first_manifest.input_id, "fake", "test"), [])
            second_extraction = extract_video(
                source,
                extraction_dir=extraction_dir,
                sample_fps=2.0,
                runner=runner,
            )
            second_manifest = discover_frames(
                second_extraction.frames_dir,
                prefix=second_extraction.prefix,
                provenance_by_filename=second_extraction.provenance_by_filename,
                identity_context=second_extraction.extraction_id,
            )

            with self.assertRaises(ProgressMismatchError):
                progress.load(
                    second_manifest,
                    ProgressMetadata(second_manifest.input_id, "fake", "test"),
                )

    def test_failed_extraction_does_not_publish_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "broken.mp4"
            source.write_bytes(b"video")
            extraction_dir = root / "frames"
            runner = FakeMediaRunner(failure=ExtractionError("decoder failed"))
            with self.assertRaisesRegex(ExtractionError, "decoder failed"):
                extract_video(source, extraction_dir=extraction_dir, runner=runner)
            self.assertFalse(extraction_dir.exists())

    def test_process_video_routes_frames_and_provenance_to_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            runner = FakeMediaRunner(duration=0.1)
            outcomes = process_video(
                str(source),
                extraction_dir=str(root / "frames"),
                save_results=False,
                analyzer_type="fake",
                analyzer_model="test",
                analyzer=FakeAnalyzer(AnalyzerResult(80, "clear")),
                runner=runner,
            )
            result = json.loads((root / "frame_analysis_results.json").read_text(encoding="utf-8"))
            self.assertEqual(len(outcomes), 3)
            self.assertEqual(result["frames"][0]["provenance"]["source_id"], "source-id")
            self.assertEqual(result["frames"][0]["provenance"]["stream_index"], 0)
            self.assertEqual(result["frames"][0]["provenance"]["timestamp_seconds"], 0.0)

    def test_process_video_supports_custom_artifact_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            output = root / "review"
            progress = root / "custom-progress.json"
            results = root / "custom-results.json"
            process_video(
                str(source),
                extraction_dir=str(root / "frames"),
                output_dir=str(output),
                progress_file=str(progress),
                results_file=str(results),
                sample_fps=1.0,
                analyzer_type="fake",
                analyzer_model="test",
                analyzer=FakeAnalyzer(AnalyzerResult(80, "clear")),
                runner=FakeMediaRunner(duration=1.0),
            )
            self.assertTrue(progress.exists())
            self.assertTrue(results.exists())
            self.assertTrue((output / "001_rawFrames000001.png").exists())

    def test_cli_exposes_video_mode_and_rejects_mixed_sources(self):
        parser = build_parser()
        args = parser.parse_args(["--video", "clip.mp4"])
        self.assertEqual(args.video, "clip.mp4")
        self.assertIsNone(args.frames_dir)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--video", "clip.mp4", "--frames-dir", "frames"])

    def test_main_rejects_missing_video_before_model_initialization(self):
        self.assertNotEqual(main(["--video", "missing-video.mp4"]), 0)


if __name__ == "__main__":
    unittest.main()
