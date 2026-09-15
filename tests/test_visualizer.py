from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from frame_clarity.visualizer import (
    MAX_DISPLAY_CANDIDATES,
    RunCoordinator,
    create_server,
    production_workflow,
    safe_filename,
    validate_sample_fps,
)


def _write_fake_result(workspace, failed=False):
    workspace.extraction.mkdir(parents=True, exist_ok=True)
    workspace.candidates.mkdir(parents=True, exist_ok=True)
    (workspace.extraction / "video_extraction_manifest.json").write_text("{}", encoding="utf-8")
    frames = []
    frame_values = []
    for index, score in ((2, 80), (1, 80), (3, 90)):
        filename = "rawFrames%06d.png" % index
        frame_values.append({
            "filename": filename,
            "frame_index": index,
            "status": "success",
            "score": score,
            "reasoning": "clear",
            "error": None,
            "attempts": 1,
            "provenance": {
                "source_id": "source",
                "source_name": "clip.mp4",
                "stream_index": 0,
                "timestamp_seconds": index / 5.0,
            },
        })
    frame_values.sort(key=lambda frame: (-frame["score"], frame["frame_index"]))
    for rank, frame in enumerate(frame_values, start=1):
        frames.append(frame)
        (workspace.candidates / ("%03d_%s" % (rank, frame["filename"]))).write_bytes(b"png")
    if failed:
        frames.append({
            "filename": "rawFrames000004.png",
            "frame_index": 4,
            "status": "failed",
            "score": None,
            "reasoning": "",
            "error": "bad frame",
            "attempts": 1,
        })
    workspace.progress.write_text(json.dumps({"frames": frames}), encoding="utf-8")
    workspace.results.write_text(json.dumps({"frames": frames}), encoding="utf-8")


class FakeWorkflow:
    def __init__(self, failed=False):
        self.failed = failed
        self.calls = []

    def __call__(self, source, workspace, sample_fps, on_phase):
        self.calls.append((source, workspace, sample_fps))
        on_phase("validation")
        on_phase("extraction")
        on_phase("analysis")
        _write_fake_result(workspace, failed=self.failed)
        if self.failed:
            raise RuntimeError("unexpected details should not be exposed")


class VisualizerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.workflow = FakeWorkflow()
        self.coordinator = RunCoordinator(
            base_dir=Path(self.tempdir.name),
            max_upload_bytes=32,
            workflow=self.workflow,
        )
        self.server = create_server(coordinator=self.coordinator)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%s" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def request(self, method, path, body=None, headers=None):
        request = Request(self.base + path, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def raw_request(self, method, path):
        request = Request(self.base + path, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    def test_upload_poll_results_and_rank_scoped_image(self):
        status, started = self.request(
            "POST",
            "/api/runs",
            body=b"video",
            headers={"Content-Length": "5", "X-Video-Filename": "../secret clip.mp4", "X-Sample-Fps": "5"},
        )
        self.assertEqual(status, 202)
        run_id = started["run_id"]
        for _ in range(30):
            status, payload = self.request("GET", "/api/runs/%s/status" % run_id)
            if payload["terminal"]:
                break
            time.sleep(0.01)
        self.assertEqual(status, 200)
        self.assertEqual(payload["phase"], "complete")
        self.assertEqual(self.workflow.calls[0][2], 5.0)
        status, result = self.request("GET", "/api/runs/%s/results" % run_id)
        self.assertEqual(status, 200)
        self.assertEqual([item["frame_index"] for item in result["candidates"]], [3, 1, 2])
        self.assertEqual(result["candidates"][0]["image_url"], "/api/runs/%s/candidates/1" % run_id)
        status, body = self.raw_request("GET", "/api/runs/%s/candidates/1" % run_id)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"png")

    def test_rejects_concurrent_uploads_and_out_of_range_sampling(self):
        record = self.coordinator.reserve_upload("clip.mp4", 5, 1)
        self.assertIsNotNone(record)
        status, payload = self.request(
            "POST", "/api/runs", body=b"x", headers={"Content-Length": "1", "X-Video-Filename": "second.mp4", "X-Sample-Fps": "31"}
        )
        self.assertEqual(status, 400)
        self.assertIn("between 5 and 30", payload["error"])
        status, payload = self.request(
            "POST", "/api/runs", body=b"x", headers={"Content-Length": "1", "X-Video-Filename": "second.mp4", "X-Sample-Fps": "5"}
        )
        self.assertEqual(status, 409)
        self.assertIn("already active", payload["error"])

    def test_upload_limit_and_path_traversal_are_rejected(self):
        status, payload = self.request(
            "POST", "/api/runs", body=b"123456789012345678901234567890123", headers={"Content-Length": "33", "X-Video-Filename": "clip.mp4", "X-Sample-Fps": "5"}
        )
        self.assertEqual(status, 400)
        self.assertIn("size limit", payload["error"])
        status, payload = self.request("GET", "/api/runs/not-a-run/candidates/../1")
        self.assertEqual(status, 404)

    def test_partial_results_remain_available_after_worker_failure(self):
        coordinator = RunCoordinator(
            base_dir=Path(self.tempdir.name),
            workflow=FakeWorkflow(failed=True),
        )
        record = coordinator.reserve_upload("clip.mp4", 5, 5)
        record.workspace.source.write_bytes(b"video")
        coordinator.start(record)
        record.worker.join(timeout=2)
        status = coordinator.status(record.run_id)
        self.assertEqual(status["phase"], "failed")
        self.assertEqual(status["progress"]["successful"], 3)
        result = coordinator.results(record.run_id)
        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["error"], "Processing failed unexpectedly")

    def test_clear_removes_run_workspace(self):
        status, started = self.request(
            "POST", "/api/runs", body=b"video", headers={"Content-Length": "5", "X-Video-Filename": "clip.mp4"}
        )
        self.assertEqual(status, 202)
        run_id = started["run_id"]
        for _ in range(30):
            record = self.coordinator.get(run_id)
            if record and record.terminal:
                root = record.workspace.root
                break
            time.sleep(0.01)
        status, _ = self.request("DELETE", "/api/runs/%s" % run_id)
        self.assertEqual(status, 200)
        self.assertFalse(root.exists())

    def test_helpers_and_production_adapter_contract(self):
        self.assertEqual(safe_filename("../../my clip.mov"), "my_clip.mov")
        self.assertEqual(validate_sample_fps("30"), 30.0)
        with self.assertRaises(ValueError):
            validate_sample_fps(4)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            workspace = self.coordinator.reserve_upload("clip.mp4", 5, 5).workspace
            calls = []

            def fake_process_video(*args, **kwargs):
                calls.append((args, kwargs))

            import frame_clarity.visualizer as visualizer
            original = visualizer.process_video
            visualizer.process_video = fake_process_video
            try:
                production_workflow(source, workspace, 15, lambda phase: None)
            finally:
                visualizer.process_video = original
            kwargs = calls[0][1]
            self.assertEqual(kwargs["analyzer_type"], "clip")
            self.assertEqual(kwargs["sample_fps"], 15)
            self.assertEqual(kwargs["progress_file"], str(workspace.progress))
            self.assertEqual(kwargs["results_file"], str(workspace.results))
            self.assertEqual(kwargs["output_dir"], str(workspace.candidates))
            self.assertEqual(kwargs["top_n"], MAX_DISPLAY_CANDIDATES)


if __name__ == "__main__":
    unittest.main()
