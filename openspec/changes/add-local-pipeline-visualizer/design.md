## Context

See `proposal.md` for the motivation and `specs/local-pipeline-visualizer/spec.md`
for the observable contract. The repository currently has a CLI adapter around
the reusable video extraction and frame-analysis workflow. `process_video` is
synchronous, extraction and analysis publish artifacts to filesystem paths, and
analysis progress is checkpointed in atomic JSON after each batch. There is no
web dependency, server lifecycle, or persistent job registry.

The visualizer is an engineer utility, not a customer-facing memory or review
system. It must remain loopback-only, local-CLIP-only, offline-testable, and
compatible with the existing CLI and video provenance contracts.

## Goals / Non-Goals

**Goals:**

- Provide a small browser interface over one isolated video-processing run.
- Keep HTTP handling and job state separate from the existing extraction and
  analysis workflow while reusing that workflow as the only processing path.
- Make long-running work observable without holding an upload request open.
- Present deterministic ranked candidates and explicit failures with enough
  metadata to judge selection quality.
- Keep source media and derived artifacts scoped to a temporary local run.
- Test the web boundary with local fakes without initializing CLIP or contacting
  external services.

**Non-Goals:**

- Customer authentication, hosted upload, multi-user access, or cloud storage.
- A persistent run history, database, gallery, or review-decision workflow.
- OpenAI or any other external analyzer in the web interface.
- Source-video playback, timeline seeking, or editing controls.
- Cancellation, pause/resume controls, or concurrent web runs in the first
  version.

## Decisions

### Use a standard-library local server

Implement the web adapter with Python standard-library HTTP facilities and
vanilla browser assets rather than adding Flask, Streamlit, or a frontend build
system. The project already has a dependency-heavy model runtime, but no web
runtime; the utility needs only a few local routes and should remain easy to
start from the repository's Python environment.

The server binds to `127.0.0.1` and chooses an available port by default,
printing the browser URL. A port option may be provided for local convenience,
but there is no general host option in the first version. A raw request body is
used for the selected video upload, with the browser-provided filename passed as
metadata; this avoids a deprecated multipart parser while retaining streaming
write control. The server validates request size while streaming to disk and
does not trust the browser MIME type.

Flask is rejected for now because a dependency and framework lifecycle would be
larger than the visualizer's narrow route surface. Streamlit and Gradio are
rejected because they introduce a larger presentation runtime and obscure the
artifact-serving and loopback security boundaries.

### Keep one in-memory run and one background worker

The server owns an in-memory current-run record containing a generated run ID,
phase, selected filename, sampling setting, counters, error state, and paths to
the run workspace. It accepts one active run and disables or rejects additional
submissions until the current run is cleared or reaches a terminal state.

After the upload is safely written, a background worker invokes the existing
video workflow with explicit run-scoped extraction, progress, results, and
copied-frame paths. Production web runs always select `clip`; test code injects
a fake workflow or analyzer at the boundary rather than exposing a fake mode in
the browser.

The upload request returns once the input is stored and the job is queued. The
browser polls a status endpoint. The worker updates coarse phases around the
workflow and reads the atomic progress file for processed, successful, and
failed counts once analysis has begun. Extraction remains an indeterminate
phase until the complete extraction manifest is available because the current
FFmpeg runner does not expose progress callbacks.

A subprocess invocation of the CLI was considered. It would improve process
isolation and cancellation, but would make structured progress and result
handling depend on parsing console output and would provide less direct access
to the existing workflow seams. Direct invocation in a single controlled worker
is preferable for this local prototype.

### Isolate every run and serve by rank

Each accepted upload receives a temporary workspace containing the uploaded
source, extraction directory, progress file, results file, and copied candidate
frames. The web adapter passes these paths explicitly instead of allowing the
CLI's source-directory defaults to write beside an arbitrary developer file.
The existing resume behavior remains enabled inside that workspace, although a
new browser submission creates a new workspace and does not reuse an earlier
run.

The result document is the display source of truth. Successful results are
rendered in the same deterministic order produced by the existing ranking
function. The web adapter uses a small fixed display window of the highest-ranked
successful candidates, configured as 12 for a manageable inspection screen,
while failed and skipped outcomes remain available in the failure summary.

Candidate images are served through a run ID and numeric candidate rank. The
server resolves that rank to the already copied frame after checking that the
resolved path remains inside the run's candidate directory. It never accepts a
filesystem path or arbitrary filename as a resource identifier.

On explicit clear or orderly server shutdown, the workspace is removed. Shutdown
waits for the worker to stop using the workspace before cleanup; an incomplete
run is never presented as a successful result. No run registry survives a
process restart.

### Keep the browser surface narrow and honest

The page contains one file picker, a bounded sampling selector with `5 FPS`
selected by default and `30 FPS` as the maximum, a start action, a status region,
and a responsive ranked candidate grid. The current CLIP model identity is
displayed as local processing information rather than offered as an analyzer
selector. The page labels scores as heuristic ranking signals and shows source
timestamps and CLIP reasoning when available.

The interface includes an explicit local-processing notice. Video bytes are
sent only to the loopback server and the selected web analyzer never sends
imagery to OpenAI or another external analyzer. The notice may explain that the
local CLIP model itself can require a one-time model download; this does not
change the local-media boundary.

### Preserve failure and partial-result semantics

The worker maps expected workflow exceptions to a sanitized terminal diagnostic.
If analysis writes a valid results file before reporting unresolved frame
failures, the UI shows the ranked successful candidates together with a failed
run state and failure summary. If validation or extraction fails before results
exist, the UI shows only the diagnostic and does not fabricate candidates.

Unexpected worker exceptions are also converted to a generic sanitized failure
for the browser and retained in server diagnostics without exposing credentials
or arbitrary request data. The web adapter does not reinterpret failed or
skipped outcomes as scores.

### Test through injectable workflow boundaries

HTTP tests use an ephemeral loopback port and local temporary directories. The
job runner is injectable so tests can simulate accepted, progressing, completed,
partially failed, and rejected runs without loading CLIP or running FFmpeg.
Tests cover upload-size rejection, single-run coordination, status polling,
ranked result serialization, candidate image serving, path traversal rejection,
cleanup, and sanitized failure reporting. A workflow integration test verifies
that the production adapter selects CLIP, passes the web sampling value, and
uses explicit run-scoped artifact paths while the fake analyzer keeps the test
offline.

## Risks / Trade-offs

- [Risk] A synchronous CLIP/FFmpeg workflow can run for a long time and cannot
  be safely interrupted from a browser button. -> Mitigation: run it outside
  the HTTP request, expose phase and checkpoint counts, and make cancellation a
  future process-worker decision rather than pretending a thread can be killed.

- [Risk] The default 5 FPS web setting may not expose duplicate-selection or
  high-density behavior found at 30 FPS. -> Mitigation: keep 30 FPS available,
  display the selected sampling setting, and leave the CLI's 30 FPS behavior
  unchanged.

- [Risk] Temporary artifacts can be large, especially at 30 FPS. -> Mitigation:
  enforce the configured upload limit, retain the existing 180-second video
  limit and maximum sampling bound, isolate artifacts, and clean them on clear
  or shutdown.

- [Risk] A loopback server has no application authentication and may be reached
  by other local processes. -> Mitigation: bind only to loopback, use opaque run
  IDs, reject arbitrary paths, avoid persistent history, and document that this
  is not a hosted authorization boundary.

- [Risk] Browser requests may outlive a page reload while the worker continues.
  -> Mitigation: keep terminal state in the process-local run record, allow the
  current run to be polled again, and clean up only after the worker has stopped.

- [Risk] Displaying only the highest-ranked candidates can hide broad ranking
  behavior. -> Mitigation: retain the complete JSON result and failure summary
  in the run workspace, while keeping the first visualizer view intentionally
  small; broader inspection can be proposed separately.

## Migration Plan

1. Add the local server, browser assets, run-state adapter, and offline HTTP
   tests without changing existing CLI modules or defaults.
2. Add a documented local startup command and explain the 5-to-30 FPS web range,
   local CLIP behavior, temporary artifact cleanup, and non-customer scope.
3. Run the default offline test suite and a manual smoke test with FFmpeg and a
   locally available CLIP model when those optional prerequisites are present.
4. Roll back by removing or disabling only the web entry point and its assets;
   the existing CLI, video workflow, progress files, results, and analyzer
   options remain usable.
