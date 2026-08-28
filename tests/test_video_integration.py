from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from frame_clarity.errors import VideoInputError
from frame_clarity.video import FFmpegRunner, extract_video


RUN_INTEGRATION = os.getenv("RUN_FFMPEG_INTEGRATION") == "1"
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@unittest.skipUnless(
    RUN_INTEGRATION and HAS_FFMPEG,
    "set RUN_FFMPEG_INTEGRATION=1 with ffmpeg and ffprobe installed",
)
class RealFfmpegTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        root = Path(cls.tempdir.name)
        cls.short = root / "short.mp4"
        cls.boundary = root / "boundary.mp4"
        cls.long = root / "long.mp4"
        for output, duration in (
            (cls.short, "1"),
            (cls.boundary, "180"),
            (cls.long, "181"),
        ):
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=size=2x2:rate=30:color=red",
                    "-t",
                    duration,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    "-y",
                    str(output),
                ],
                check=True,
            )
        cls.broken = root / "broken.mp4"
        cls.broken.write_bytes(b"not a video")

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_short_video_extracts_with_expected_default_density(self):
        extraction = extract_video(self.short, extraction_dir=Path(self.tempdir.name) / "short_frames")
        self.assertEqual(extraction.frame_count, 30)

    def test_three_minute_video_is_accepted(self):
        probe = FFmpegRunner().probe(self.boundary)
        self.assertLessEqual(probe.duration_seconds, 180.0)

    def test_video_over_three_minutes_is_rejected(self):
        with self.assertRaises(VideoInputError):
            FFmpegRunner().probe(self.long)

    def test_decoder_failure_is_reported(self):
        with self.assertRaises(VideoInputError):
            FFmpegRunner().probe(self.broken)


if __name__ == "__main__":
    unittest.main()
