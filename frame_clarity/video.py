"""Local FFmpeg video probing and deterministic frame extraction."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence

from .discovery import configured_prefix, discover_frames
from .errors import DiscoveryError, ExtractionError, VideoInputError
from .models import FrameManifest, FrameProvenance
from .storage import atomic_write_json, read_json


DEFAULT_SAMPLE_FPS = 30.0
MAX_VIDEO_DURATION_SECONDS = 180.0
EXTRACTION_VERSION = 1
EXTRACTION_MANIFEST_NAME = "video_extraction_manifest.json"
DEFAULT_EXTRACTION_TIMEOUT_SECONDS = 600.0
MAX_DIAGNOSTIC_LENGTH = 1000
MAX_COMMAND_OUTPUT_LENGTH = 1024 * 1024


@dataclass(frozen=True)
class MediaCommandResult:
    """Small subprocess result contract used by the injectable media runner."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class VideoProbe:
    """Validated source metadata needed to build an extraction plan."""

    path: Path
    source_id: str
    source_name: str
    duration_seconds: float
    stream_index: int
    stream: Dict[str, Any]


class VideoMediaRunner(Protocol):
    """Boundary for probing and extracting video media."""

    identity: str
    version: str

    def probe(self, video_path: Path) -> VideoProbe:
        ...

    def extract(
        self,
        probe: VideoProbe,
        output_dir: Path,
        prefix: str,
        sample_fps: float,
        expected_frames: int,
    ) -> None:
        ...


def _diagnostic(value: object) -> str:
    message = str(value).strip() or value.__class__.__name__
    return message[:MAX_DIAGNOSTIC_LENGTH]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise VideoInputError("Could not read video %s: %s" % (path.name, exc)) from exc
    return digest.hexdigest()


def _resolve_executable(value: str, label: str) -> str:
    resolved = shutil.which(value)
    if resolved is None:
        raise VideoInputError("Could not find %s executable: %s" % (label, value))
    return resolved


def _subprocess_runner(argv: Sequence[str], timeout: float) -> MediaCommandResult:
    try:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
            )
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.wait()
                raise ExtractionError(
                    "Media command timed out after %s seconds" % timeout
                ) from exc
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(MAX_COMMAND_OUTPUT_LENGTH + 1)
            stderr = stderr_file.read(MAX_COMMAND_OUTPUT_LENGTH + 1)
    except ExtractionError:
        raise
    except OSError as exc:
        raise ExtractionError("Could not start media command: %s" % exc) from exc
    return MediaCommandResult(
        returncode=process.returncode,
        stdout=stdout.decode("utf-8", "replace"),
        stderr=stderr.decode("utf-8", "replace"),
    )


class FFmpegRunner:
    """FFprobe/FFmpeg subprocess implementation of the media boundary."""

    identity = "ffmpeg"

    def __init__(
        self,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        timeout_seconds: float = DEFAULT_EXTRACTION_TIMEOUT_SECONDS,
        run_fn: Optional[Callable[[Sequence[str], float], MediaCommandResult]] = None,
    ) -> None:
        if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
            raise VideoInputError("Video extraction timeout must be positive")
        self.ffmpeg = _resolve_executable(ffmpeg, "ffmpeg") if run_fn is None else ffmpeg
        self.ffprobe = _resolve_executable(ffprobe, "ffprobe") if run_fn is None else ffprobe
        self.timeout_seconds = timeout_seconds
        self._run = run_fn or _subprocess_runner
        self.version = Path(self.ffmpeg).name

    def _execute(self, argv: Sequence[str], label: str) -> MediaCommandResult:
        try:
            result = self._run(argv, self.timeout_seconds)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError("Could not run %s: %s" % (label, _diagnostic(exc))) from exc
        if not isinstance(result, MediaCommandResult):
            try:
                result = MediaCommandResult(
                    returncode=int(getattr(result, "returncode")),
                    stdout=str(getattr(result, "stdout", "") or ""),
                    stderr=str(getattr(result, "stderr", "") or ""),
                )
            except (TypeError, ValueError, AttributeError) as exc:
                raise ExtractionError("%s returned an invalid command result" % label) from exc
        if result.returncode != 0:
            detail = _diagnostic(result.stderr or result.stdout)
            raise ExtractionError("%s failed%s" % (label, ": %s" % detail if detail else ""))
        return result

    def probe(self, video_path: Path) -> VideoProbe:
        path = Path(video_path)
        if not path.exists():
            raise VideoInputError("Video file does not exist: %s" % path)
        if not path.is_file():
            raise VideoInputError("Video path is not a regular file: %s" % path)
        if not os.access(str(path), os.R_OK):
            raise VideoInputError("Video file is not readable: %s" % path)
        resolved = path.resolve()
        result = self._execute(
            [
                self.ffprobe,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(resolved),
            ],
            "ffprobe",
        )
        try:
            payload = json.loads(result.stdout)
        except (TypeError, ValueError) as exc:
            raise VideoInputError("ffprobe returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise VideoInputError("ffprobe output must be a JSON object")
        streams = payload.get("streams")
        if not isinstance(streams, list):
            raise VideoInputError("ffprobe output did not contain streams")
        stream = None
        for value in streams:
            if not isinstance(value, dict) or value.get("codec_type") != "video":
                continue
            disposition = value.get("disposition")
            attached_picture = (
                int(disposition.get("attached_pic", 0) or 0)
                if isinstance(disposition, dict)
                else 0
            )
            if attached_picture != 1:
                stream = value
                break
        if stream is None:
            raise VideoInputError("Video does not contain a usable video stream")
        try:
            stream_index = int(stream["index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VideoInputError("ffprobe video stream did not contain a valid index") from exc

        format_payload = payload.get("format")
        if not isinstance(format_payload, dict):
            format_payload = {}
        duration_value = format_payload.get("duration", stream.get("duration"))
        try:
            duration = float(duration_value)
        except (TypeError, ValueError) as exc:
            raise VideoInputError("Video duration could not be determined") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise VideoInputError("Video duration could not be determined")
        if duration > MAX_VIDEO_DURATION_SECONDS:
            raise VideoInputError(
                "Video duration %.3f seconds exceeds the %.0f-second limit"
                % (duration, MAX_VIDEO_DURATION_SECONDS)
            )
        source_id = _sha256_file(resolved)
        stream_context = {
            key: stream[key]
            for key in (
                "index",
                "codec_name",
                "codec_long_name",
                "width",
                "height",
                "pix_fmt",
                "time_base",
                "start_time",
                "avg_frame_rate",
                "r_frame_rate",
            )
            if key in stream
        }
        return VideoProbe(
            path=resolved,
            source_id=source_id,
            source_name=path.name,
            duration_seconds=duration,
            stream_index=stream_index,
            stream=stream_context,
        )

    def extract(
        self,
        probe: VideoProbe,
        output_dir: Path,
        prefix: str,
        sample_fps: float,
        expected_frames: int,
    ) -> None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        pattern = output / (prefix + "%06d.png")
        self._execute(
            [
                self.ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-autorotate",
                "-i",
                str(probe.path),
                "-map",
                "0:%s" % probe.stream_index,
                "-an",
                "-sn",
                "-dn",
                "-vf",
                "fps=%s,format=rgb24" % _format_fps(sample_fps),
                "-frames:v",
                str(expected_frames),
                str(pattern),
            ],
            "ffmpeg",
        )


@dataclass(frozen=True)
class VideoExtraction:
    """A complete extracted frame workspace and its provenance mapping."""

    frames_dir: Path
    manifest_path: Path
    extraction_id: str
    prefix: str
    provenance_by_filename: Mapping[str, FrameProvenance]
    frame_count: int


def _format_fps(sample_fps: float) -> str:
    return format(sample_fps, ".12g")


def _expected_frame_count(duration: float, sample_fps: float) -> int:
    return max(1, int(math.ceil(duration * sample_fps - 1e-9)))


def _extraction_id(
    probe: VideoProbe,
    prefix: str,
    sample_fps: float,
    extractor: str,
    extractor_version: str,
) -> str:
    payload = {
        "version": EXTRACTION_VERSION,
        "source_id": probe.source_id,
        "stream_index": probe.stream_index,
        "stream": probe.stream,
        "sampling_fps": sample_fps,
        "prefix": prefix,
        "extractor": extractor,
        "extractor_version": extractor_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _provenance_for_frames(
    probe: VideoProbe,
    extraction_id: str,
    prefix: str,
    sample_fps: float,
    extractor: str,
    extractor_version: str,
    frame_count: int,
) -> Dict[str, FrameProvenance]:
    return {
        "%s%06d.png" % (prefix, index): FrameProvenance(
            source_id=probe.source_id,
            source_name=probe.source_name,
            stream_index=probe.stream_index,
            requested_timestamp_seconds=(index - 1) / sample_fps,
            sampling_fps=sample_fps,
            extraction_id=extraction_id,
            extractor=extractor,
            extractor_version=extractor_version,
            stream=dict(probe.stream),
        )
        for index in range(1, frame_count + 1)
    }


def _manifest_payload(
    probe: VideoProbe,
    extraction_id: str,
    prefix: str,
    sample_fps: float,
    extractor: str,
    extractor_version: str,
    provenance_by_filename: Mapping[str, FrameProvenance],
) -> Dict[str, Any]:
    return {
        "version": EXTRACTION_VERSION,
        "complete": True,
        "extraction_id": extraction_id,
        "source": {
            "source_id": probe.source_id,
            "source_name": probe.source_name,
            "duration_seconds": probe.duration_seconds,
            "stream_index": probe.stream_index,
            "stream": dict(probe.stream),
        },
        "sampling": {"fps": sample_fps, "prefix": prefix},
        "extractor": {"name": extractor, "version": extractor_version},
        "frames": [
            {
                "filename": filename,
                "frame_index": index,
                "provenance": provenance.to_dict(),
            }
            for index, (filename, provenance) in enumerate(
                sorted(provenance_by_filename.items()), start=1
            )
        ],
    }


def _load_existing(
    directory: Path,
    expected_id: str,
    expected_prefix: str,
    expected_count: int,
) -> Optional[VideoExtraction]:
    manifest_path = directory / EXTRACTION_MANIFEST_NAME
    if not directory.is_dir() or not manifest_path.is_file():
        return None
    try:
        payload = read_json(manifest_path, ExtractionError)
        if not isinstance(payload, dict) or payload.get("complete") is not True:
            return None
        if payload.get("version") != EXTRACTION_VERSION:
            return None
        if payload.get("extraction_id") != expected_id:
            return None
        sampling = payload.get("sampling")
        if not isinstance(sampling, dict) or sampling.get("prefix") != expected_prefix:
            return None
        raw_frames = payload.get("frames")
        if not isinstance(raw_frames, list) or len(raw_frames) != expected_count:
            return None
        provenance_by_filename: Dict[str, FrameProvenance] = {}
        for value in raw_frames:
            if not isinstance(value, dict) or "filename" not in value or "provenance" not in value:
                return None
            filename = str(value["filename"])
            provenance_by_filename[filename] = FrameProvenance.from_dict(value["provenance"])
        if len(provenance_by_filename) != expected_count:
            return None
        discover_frames(
            directory,
            prefix=expected_prefix,
            provenance_by_filename=provenance_by_filename,
            identity_context=expected_id,
        )
    except (DiscoveryError, ExtractionError, ValueError, TypeError, KeyError):
        return None
    extractor = payload.get("extractor")
    if not isinstance(extractor, dict):
        return None
    return VideoExtraction(
        frames_dir=directory,
        manifest_path=manifest_path,
        extraction_id=expected_id,
        prefix=expected_prefix,
        provenance_by_filename=provenance_by_filename,
        frame_count=expected_count,
    )


def _validate_pngs(directory: Path, expected_names: Sequence[str]) -> None:
    actual_names = sorted(path.name for path in directory.glob("*.png"))
    if actual_names != list(expected_names):
        raise ExtractionError(
            "Extraction produced an unexpected frame set: expected %s frame(s), found %s"
            % (len(expected_names), len(actual_names))
        )
    try:
        from PIL import Image
    except Exception as exc:
        raise ExtractionError("Pillow is required to validate extracted PNG frames") from exc
    for filename in expected_names:
        path = directory / filename
        try:
            with Image.open(str(path)) as image:
                image.verify()
        except Exception as exc:
            raise ExtractionError("Extracted frame is unreadable: %s" % filename) from exc


def _retire_existing(directory: Path) -> Optional[Path]:
    if not directory.exists():
        return None
    backup = directory.parent / (".%s.previous-%s" % (directory.name, uuid.uuid4().hex))
    try:
        os.replace(str(directory), str(backup))
    except OSError as exc:
        raise ExtractionError("Could not isolate existing extraction: %s" % exc) from exc
    return backup


def _cleanup_path(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        if path.is_dir():
            shutil.rmtree(str(path))
        else:
            path.unlink()
    except OSError:
        pass


def extract_video(
    video_path: Path,
    *,
    extraction_dir: Optional[Path] = None,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
    resume: bool = True,
    prefix: Optional[str] = None,
    runner: Optional[VideoMediaRunner] = None,
) -> VideoExtraction:
    """Probe and extract a complete, reusable frame workspace."""

    if not math.isfinite(sample_fps) or sample_fps <= 0:
        raise VideoInputError("Video sampling rate must be positive")
    frame_prefix = configured_prefix(prefix)
    media_runner = runner or FFmpegRunner()
    probe = media_runner.probe(Path(video_path))
    if not math.isfinite(probe.duration_seconds) or probe.duration_seconds <= 0:
        raise VideoInputError("Video duration could not be determined")
    if probe.duration_seconds > MAX_VIDEO_DURATION_SECONDS:
        raise VideoInputError(
            "Video duration %.3f seconds exceeds the %.0f-second limit"
            % (probe.duration_seconds, MAX_VIDEO_DURATION_SECONDS)
        )
    expected_count = _expected_frame_count(probe.duration_seconds, sample_fps)
    extractor = getattr(media_runner, "identity", "ffmpeg")
    extractor_version = getattr(media_runner, "version", "")
    extraction_id = _extraction_id(
        probe, frame_prefix, sample_fps, extractor, extractor_version
    )
    final_dir = (
        Path(extraction_dir)
        if extraction_dir is not None
        else probe.path.parent / (probe.path.stem + "_frames")
    )
    if final_dir.exists() and resume:
        existing = _load_existing(final_dir, extraction_id, frame_prefix, expected_count)
        if existing is not None:
            return existing

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary: Optional[Path] = Path(
        tempfile.mkdtemp(prefix=".%s.tmp-" % final_dir.name, dir=str(final_dir.parent))
    )
    previous: Optional[Path] = None
    try:
        media_runner.extract(
            probe,
            temporary,
            frame_prefix,
            sample_fps,
            expected_count,
        )
        expected_names = [
            "%s%06d.png" % (frame_prefix, index)
            for index in range(1, expected_count + 1)
        ]
        _validate_pngs(temporary, expected_names)
        provenance_by_filename = _provenance_for_frames(
            probe,
            extraction_id,
            frame_prefix,
            sample_fps,
            extractor,
            extractor_version,
            expected_count,
        )
        manifest = discover_frames(
            temporary,
            prefix=frame_prefix,
            provenance_by_filename=provenance_by_filename,
            identity_context=extraction_id,
        )
        if len(manifest.items) != expected_count:
            raise ExtractionError(
                "Extraction produced %s frame(s); expected %s"
                % (len(manifest.items), expected_count)
            )
        atomic_write_json(
            temporary / EXTRACTION_MANIFEST_NAME,
            _manifest_payload(
                probe,
                extraction_id,
                frame_prefix,
                sample_fps,
                extractor,
                extractor_version,
                provenance_by_filename,
            ),
            ExtractionError,
        )
        previous = _retire_existing(final_dir)
        os.replace(str(temporary), str(final_dir))
        temporary = None
        _cleanup_path(previous)
        return VideoExtraction(
            frames_dir=final_dir,
            manifest_path=final_dir / EXTRACTION_MANIFEST_NAME,
            extraction_id=extraction_id,
            prefix=frame_prefix,
            provenance_by_filename=provenance_by_filename,
            frame_count=expected_count,
        )
    except BaseException:
        _cleanup_path(temporary)
        raise
