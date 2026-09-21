"""Loopback-only browser adapter for inspecting one local video run."""

from __future__ import annotations

import json
import math
import mimetypes
import re
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlsplit

from .cli import process_video
from .errors import FrameClarityError


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0
DEFAULT_WEB_SAMPLE_FPS = 5.0
MIN_WEB_SAMPLE_FPS = 5.0
MAX_WEB_SAMPLE_FPS = 30.0
WEB_SAMPLE_CHOICES = (5, 10, 15, 20, 25, 30)
DEFAULT_MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_DIAGNOSTIC_LENGTH = 1000
MAX_FILENAME_LENGTH = 120
MAX_DISPLAY_CANDIDATES = 12
UPLOAD_CHUNK_SIZE = 1024 * 1024
WORKER_SHUTDOWN_TIMEOUT_SECONDS = 5.0
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def _diagnostic(value: object, workspace: Optional["RunWorkspace"] = None) -> str:
    message = str(value).strip() or value.__class__.__name__
    if workspace is not None:
        for path in (workspace.root, workspace.source):
            message = message.replace(str(path), "[run]")
    message = re.sub(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/)[^\s,;]+", "[path]", message)
    return message[:MAX_DIAGNOSTIC_LENGTH]


def safe_filename(value: str) -> str:
    """Return a non-path filename suitable for a temporary upload."""

    candidate = Path(str(value).replace("\x00", "")).name
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._")
    if not candidate or candidate in {".", ".."}:
        candidate = "video.bin"
    return candidate[:MAX_FILENAME_LENGTH]


def validate_sample_fps(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("sampling FPS must be a number from 5 through 30") from exc
    if not math.isfinite(parsed) or not MIN_WEB_SAMPLE_FPS <= parsed <= MAX_WEB_SAMPLE_FPS:
        raise ValueError("sampling FPS must be between 5 and 30")
    return parsed


@dataclass(frozen=True)
class RunWorkspace:
    """All artifacts belonging to one ephemeral visualizer run."""

    root: Path
    source: Path
    extraction: Path
    candidates: Path
    progress: Path
    results: Path

    @classmethod
    def create(cls, base_dir: Optional[Path], filename: str) -> "RunWorkspace":
        root = Path(tempfile.mkdtemp(prefix="frame-clarity-visualizer-", dir=str(base_dir) if base_dir else None))
        source = root / "source" / safe_filename(filename)
        return cls(
            root=root,
            source=source,
            extraction=root / "extracted_frames",
            candidates=root / "candidates",
            progress=root / "frame_analysis_progress.json",
            results=root / "frame_analysis_results.json",
        )

    def prepare(self) -> None:
        self.source.parent.mkdir(parents=True, exist_ok=True)
        self.extraction.mkdir(parents=True, exist_ok=True)
        self.candidates.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        shutil.rmtree(str(self.root), ignore_errors=True)


@dataclass
class RunRecord:
    run_id: str
    filename: str
    sample_fps: float
    workspace: RunWorkspace
    phase: str = "uploading"
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    worker: Optional[threading.Thread] = None

    @property
    def terminal(self) -> bool:
        return self.phase in {"complete", "failed", "cleared"}


Workflow = Callable[[Path, RunWorkspace, float, Callable[[str], None]], None]


def production_workflow(
    source: Path,
    workspace: RunWorkspace,
    sample_fps: float,
    on_phase: Callable[[str], None],
) -> None:
    """Run the existing workflow with web-owned artifact paths and CLIP only."""

    process_video(
        str(source),
        extraction_dir=str(workspace.extraction),
        output_dir=str(workspace.candidates),
        progress_file=str(workspace.progress),
        results_file=str(workspace.results),
        sample_fps=sample_fps,
        top_n=MAX_DISPLAY_CANDIDATES,
        analyzer_type="clip",
        analyzer_model="openai/clip-vit-base-patch32",
        output_format="none",
        lifecycle_callback=on_phase,
    )


class RunCoordinator:
    """Own one in-memory run and its worker lifecycle."""

    def __init__(
        self,
        *,
        base_dir: Optional[Path] = None,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        workflow: Optional[Workflow] = None,
    ) -> None:
        if max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        self.base_dir = Path(base_dir) if base_dir else None
        self.max_upload_bytes = max_upload_bytes
        self.workflow = workflow or production_workflow
        self._lock = threading.RLock()
        self._current: Optional[RunRecord] = None

    def reserve_upload(self, filename: str, sample_fps: float, content_length: int) -> RunRecord:
        if content_length < 0 or content_length > self.max_upload_bytes:
            raise ValueError("upload exceeds the configured size limit")
        with self._lock:
            if self._current is not None and not self._current.terminal:
                raise RuntimeError("another visualizer run is already active")
            if self._current is not None:
                self._current.workspace.cleanup()
            workspace = RunWorkspace.create(self.base_dir, filename)
            workspace.prepare()
            record = RunRecord(
                run_id=uuid.uuid4().hex,
                filename=safe_filename(filename),
                sample_fps=sample_fps,
                workspace=workspace,
            )
            self._current = record
            return record

    def write_upload(self, record: RunRecord, stream, content_length: int) -> None:
        written = 0
        try:
            with record.workspace.source.open("wb") as target:
                while written < content_length:
                    chunk = stream.read(min(UPLOAD_CHUNK_SIZE, content_length - written))
                    if not chunk:
                        raise ValueError("upload ended before the declared content length")
                    written += len(chunk)
                    if written > self.max_upload_bytes:
                        raise ValueError("upload exceeds the configured size limit")
                    target.write(chunk)
        except Exception:
            self.abort(record)
            raise

    def start(self, record: RunRecord) -> None:
        with self._lock:
            if self._current is not record:
                raise RuntimeError("visualizer run is no longer current")
            record.phase = "validation"
            worker = threading.Thread(
                target=self._run,
                args=(record,),
                name="frame-clarity-visualizer",
                daemon=True,
            )
            record.worker = worker
            worker.start()

    def _run(self, record: RunRecord) -> None:
        try:
            self.workflow(record.workspace.source, record.workspace, record.sample_fps, lambda phase: self.set_phase(record, phase))
        except Exception as exc:
            with self._lock:
                record.error = _diagnostic(exc, record.workspace) if isinstance(exc, FrameClarityError) else "Processing failed unexpectedly"
                record.phase = "failed"
                record.finished_at = time.time()
        else:
            with self._lock:
                record.phase = "complete"
                record.finished_at = time.time()

    def set_phase(self, record: RunRecord, phase: str) -> None:
        with self._lock:
            if self._current is record and not record.terminal:
                record.phase = phase

    def abort(self, record: RunRecord) -> None:
        with self._lock:
            if self._current is record:
                self._current = None
            record.phase = "cleared"
            record.workspace.cleanup()

    def current(self) -> Optional[RunRecord]:
        with self._lock:
            return self._current

    def get(self, run_id: str) -> Optional[RunRecord]:
        with self._lock:
            record = self._current
            return record if record is not None and record.run_id == run_id else None

    def clear(self, run_id: str) -> None:
        with self._lock:
            record = self.get(run_id)
            if record is None:
                raise KeyError("unknown run")
            if not record.terminal:
                raise RuntimeError("active runs cannot be cleared until processing finishes")
            self._current = None
            record.phase = "cleared"
            record.workspace.cleanup()

    def shutdown(self) -> None:
        record = self.current()
        if record is not None and record.worker is not None:
            record.worker.join(timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS)
            if record.worker.is_alive():
                # Python cannot safely kill a running thread. Leave its workspace
                # intact and let the process owner force-kill a stuck worker.
                with self._lock:
                    if self._current is record:
                        self._current = None
                    record.phase = "cleared"
                return
        with self._lock:
            if self._current is not None:
                self._current.workspace.cleanup()
                self._current.phase = "cleared"
                self._current = None

    @staticmethod
    def _read_progress(record: RunRecord) -> Dict[str, int]:
        counts = {"processed": 0, "successful": 0, "failed": 0, "skipped": 0}
        try:
            payload = json.loads(record.workspace.progress.read_text(encoding="utf-8"))
            frames = payload.get("frames", []) if isinstance(payload, dict) else []
            if isinstance(frames, list):
                counts["processed"] = len(frames)
                for frame in frames:
                    if not isinstance(frame, dict):
                        continue
                    key = {"success": "successful", "failed": "failed", "skipped": "skipped"}.get(frame.get("status"))
                    if key is not None:
                        counts[key] += 1
        except (OSError, ValueError, TypeError):
            pass
        return counts

    def status(self, run_id: str) -> Dict[str, Any]:
        record = self.get(run_id)
        if record is None:
            raise KeyError("unknown run")
        phase = record.phase
        if phase == "extraction" and record.workspace.extraction.exists():
            phase = "extraction"
        elif phase in {"analysis", "analysis_complete"}:
            phase = "analysis"
        return {
            "run_id": record.run_id,
            "filename": record.filename,
            "sampling_fps": record.sample_fps,
            "phase": phase,
            "terminal": record.terminal,
            "progress": self._read_progress(record),
            "error": record.error,
        }

    def results(self, run_id: str, image_base: str = "") -> Dict[str, Any]:
        record = self.get(run_id)
        if record is None:
            raise KeyError("unknown run")
        payload: Dict[str, Any] = {}
        try:
            value = json.loads(record.workspace.results.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                payload = value
        except (OSError, ValueError, TypeError):
            pass
        frames = payload.get("frames", []) if isinstance(payload.get("frames", []), list) else []
        def sort_key(frame: Dict[str, Any]) -> Tuple[int, float, int]:
            try:
                frame_index = int(frame.get("frame_index", 0))
            except (TypeError, ValueError):
                frame_index = 0
            if frame.get("status") == "success":
                try:
                    score = float(frame.get("score", 0))
                except (TypeError, ValueError):
                    score = 0.0
                return (0, -score, frame_index)
            return (1, 0.0, frame_index)

        frames = sorted((frame for frame in frames if isinstance(frame, dict)), key=sort_key)
        candidates: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        rank = 0
        for frame in frames:
            status = frame.get("status")
            if status == "success" and rank < MAX_DISPLAY_CANDIDATES:
                rank += 1
                candidate = {
                    "rank": rank,
                    "filename": frame.get("filename"),
                    "frame_index": frame.get("frame_index"),
                    "score": frame.get("score"),
                    "reasoning": frame.get("reasoning", ""),
                    "provenance": frame.get("provenance"),
                }
                if image_base:
                    candidate["image_url"] = "%s/%s/candidates/%s" % (image_base.rstrip("/"), record.run_id, rank)
                candidates.append(candidate)
            elif status == "failed":
                failed.append({
                    "filename": frame.get("filename"),
                    "frame_index": frame.get("frame_index"),
                    "error": _diagnostic(frame.get("error") or "unknown frame failure", record.workspace),
                })
            elif status == "skipped":
                skipped.append({
                    "filename": frame.get("filename"),
                    "frame_index": frame.get("frame_index"),
                    "reason": _diagnostic(frame.get("error") or "frame skipped", record.workspace),
                })
        return {
            "run_id": record.run_id,
            "phase": record.phase,
            "candidates": candidates,
            "failed": failed,
            "skipped": skipped,
            "error": record.error,
        }

    def candidate_path(self, run_id: str, rank: int) -> Path:
        record = self.get(run_id)
        if record is None:
            raise KeyError("unknown run")
        if rank <= 0 or rank > MAX_DISPLAY_CANDIDATES:
            raise ValueError("candidate rank is outside the display range")
        results = self.results(run_id)
        candidates = results["candidates"]
        if rank > len(candidates):
            raise KeyError("unknown candidate rank")
        filename = safe_filename(str(candidates[rank - 1].get("filename") or ""))
        candidate = (record.workspace.candidates / ("%03d_%s" % (rank, filename))).resolve()
        root = record.workspace.candidates.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("candidate path is outside the run workspace") from exc
        if not candidate.is_file():
            raise KeyError("candidate image is unavailable")
        return candidate


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


class VisualizerHandler(BaseHTTPRequestHandler):
    """HTTP surface kept intentionally small and path-addressed by run/rank."""

    server: "VisualizerServer"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Dict[str, Any]) -> None:
        self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message[:MAX_DIAGNOSTIC_LENGTH]})

    def do_GET(self) -> None:
        path = unquote(urlsplit(self.path).path)
        if path == "/":
            body = self.server.index_html
            self._send(200, body, "text/html; charset=utf-8")
            return
        if path == "/assets/app.css":
            self._send(200, self.server.css, "text/css; charset=utf-8")
            return
        if path == "/assets/app.js":
            self._send(200, self.server.js, "application/javascript; charset=utf-8")
            return
        if path == "/api/runs/current/status":
            record = self.server.coordinator.current()
            if record is None:
                self._error(404, "no current run")
            else:
                self._status(record.run_id)
            return
        parts = [part for part in path.split("/") if part]
        if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "status":
            self._status(parts[2])
        elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "results":
            self._results(parts[2])
        elif len(parts) == 5 and parts[:2] == ["api", "runs"] and parts[3] == "candidates":
            self._candidate(parts[2], parts[4])
        else:
            self._error(404, "not found")

    def _status(self, run_id: str) -> None:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            self._error(404, "unknown run")
            return
        try:
            self._json(200, self.server.coordinator.status(run_id))
        except KeyError:
            self._error(404, "unknown run")

    def _results(self, run_id: str) -> None:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            self._error(404, "unknown run")
            return
        try:
            self._json(200, self.server.coordinator.results(run_id, "/api/runs"))
        except KeyError:
            self._error(404, "unknown run")

    def _candidate(self, run_id: str, raw_rank: str) -> None:
        if not RUN_ID_PATTERN.fullmatch(run_id) or not raw_rank.isdigit():
            self._error(404, "unknown candidate")
            return
        try:
            candidate = self.server.coordinator.candidate_path(run_id, int(raw_rank))
        except (KeyError, ValueError):
            self._error(404, "unknown candidate")
            return
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        try:
            self._send(200, candidate.read_bytes(), content_type)
        except OSError:
            self._error(404, "candidate image is unavailable")

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/runs":
            self._error(404, "not found")
            return
        length_header = self.headers.get("Content-Length")
        filename = self.headers.get("X-Video-Filename", "")
        try:
            if not filename.strip():
                raise ValueError("X-Video-Filename is required")
            content_length = int(length_header) if length_header is not None else -1
            sample_fps = validate_sample_fps(self.headers.get("X-Sample-Fps", DEFAULT_WEB_SAMPLE_FPS))
            if content_length < 0:
                raise ValueError("Content-Length is required")
            record = self.server.coordinator.reserve_upload(filename, sample_fps, content_length)
            self.server.coordinator.write_upload(record, self.rfile, content_length)
            self.server.coordinator.start(record)
        except RuntimeError as exc:
            self._error(409, str(exc))
        except (ValueError, TypeError) as exc:
            self._error(400, str(exc))
        except OSError as exc:
            self._error(400, _diagnostic(exc))
        else:
            self._json(202, {"run_id": record.run_id, "status_url": "/api/runs/%s/status" % record.run_id})

    def do_DELETE(self) -> None:
        path = unquote(urlsplit(self.path).path)
        parts = [part for part in path.split("/") if part]
        if len(parts) != 3 or parts[:2] != ["api", "runs"]:
            self._error(404, "not found")
            return
        run_id = parts[2]
        if not RUN_ID_PATTERN.fullmatch(run_id):
            self._error(404, "unknown run")
            return
        try:
            self.server.coordinator.clear(run_id)
        except KeyError:
            self._error(404, "unknown run")
        except RuntimeError as exc:
            self._error(409, str(exc))
        else:
            self._json(200, {"cleared": True})


class VisualizerServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: Tuple[str, int], coordinator: RunCoordinator) -> None:
        super().__init__(address, VisualizerHandler)
        self.coordinator = coordinator
        assets = Path(__file__).with_name("visualizer_assets")
        self.index_html = (assets / "index.html").read_bytes()
        self.css = (assets / "app.css").read_bytes()
        self.js = (assets / "app.js").read_bytes()

    def server_close(self) -> None:
        self.coordinator.shutdown()
        super().server_close()


def create_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    coordinator: Optional[RunCoordinator] = None,
) -> VisualizerServer:
    if host != DEFAULT_HOST:
        raise ValueError("visualizer host must be 127.0.0.1")
    return VisualizerServer((host, port), coordinator or RunCoordinator())


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the local Frame Clarity pipeline visualizer")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="loopback port (default: available port)")
    parser.add_argument("--max-upload-mb", type=float, default=DEFAULT_MAX_UPLOAD_BYTES / (1024 * 1024), help="maximum upload size in MiB")
    args = parser.parse_args(argv)
    if args.port < 0 or args.port > 65535:
        parser.error("--port must be between 0 and 65535")
    if not math.isfinite(args.max_upload_mb) or args.max_upload_mb <= 0:
        parser.error("--max-upload-mb must be positive")
    server = create_server(port=args.port, coordinator=RunCoordinator(max_upload_bytes=int(args.max_upload_mb * 1024 * 1024)))
    print("Frame Clarity local visualizer: http://%s:%s" % (server.server_address[0], server.server_address[1]), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


__all__ = [
    "DEFAULT_MAX_UPLOAD_BYTES",
    "DEFAULT_WEB_SAMPLE_FPS",
    "MAX_DISPLAY_CANDIDATES",
    "RunCoordinator",
    "RunWorkspace",
    "VisualizerServer",
    "create_server",
    "main",
    "production_workflow",
    "safe_filename",
    "validate_sample_fps",
]
