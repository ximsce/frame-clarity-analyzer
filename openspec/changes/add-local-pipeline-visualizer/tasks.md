## 1. Local Web Adapter Foundation

- [ ] 1.1 Add the documented standard-library web entry point and serve the visualizer on loopback with an available-port default.
- [ ] 1.2 Add streaming single-video upload handling with safe filename normalization, configured request-size enforcement, and isolated temporary run workspace creation.
- [ ] 1.3 Add run-scoped cleanup and lifecycle handling for explicit clear, orderly shutdown, and incomplete runs.

## 2. Pipeline Job Integration

- [ ] 2.1 Add an in-memory single-run coordinator with opaque run IDs, active-run exclusion, and terminal state tracking.
- [ ] 2.2 Invoke the existing video workflow from a background worker with explicit extraction, progress, results, and copied-frame paths, always selecting local CLIP.
- [ ] 2.3 Enforce the web sampling contract of a 5 FPS default, bounded choices through 30 FPS, and rejection of values outside the web range without changing CLI defaults.
- [ ] 2.4 Publish validation, extraction, analysis, completion, and failure state from worker lifecycle events and atomic progress artifacts, including valid partial results after analysis failures.
- [ ] 2.5 Expose ranked successful candidates using the existing deterministic result contract, a fixed top-12 display window, provenance timestamps, scores, reasoning, and separate failed/skipped summaries.

## 3. HTTP Surface And Browser View

- [ ] 3.1 Add HTTP endpoints for starting a run, polling current-run status, retrieving result metadata, clearing a run, and serving only rank-addressed candidate images.
- [ ] 3.2 Reject malformed requests, concurrent submissions, unknown run IDs, invalid candidate ranks, and path traversal attempts with clear non-success responses.
- [ ] 3.3 Add the responsive vanilla HTML, CSS, and JavaScript view with file selection, 5-to-30 FPS sampling choices, local-CLIP notice, progress states, ranked candidate cards, and failure diagnostics.
- [ ] 3.4 Ensure the browser view has no OpenAI/analyzer selector, publishing controls, approval controls, source-video preview, or sharing behavior.

## 4. Verification

- [ ] 4.1 Add offline HTTP and job-lifecycle tests using fake media/workflow boundaries for upload, sampling, single-run coordination, polling, completion, partial failure, and cleanup.
- [ ] 4.2 Add tests for deterministic candidate ordering, candidate metadata, rank-scoped image serving, path traversal rejection, and sanitized diagnostics without loading a model or contacting a service.
- [ ] 4.3 Add a production-adapter test proving web jobs pass local CLIP selection, explicit artifact paths, and the requested sampling value to the existing workflow.
- [ ] 4.4 Run `python3 -m unittest discover -s tests -v`, `python3 -m py_compile identify_clearest_frames.py`, and the visualizer startup/help smoke check without model downloads or credentials.
- [ ] 4.5 Run an optional manual FFmpeg and local-CLIP smoke test when FFmpeg, model files, and suitable local resources are available; keep it separate from the default offline suite.

## 5. Documentation And Compatibility

- [ ] 5.1 Document the local visualizer startup command, loopback-only behavior, upload/resource limits, 5 FPS default, maximum 30 FPS setting, temporary cleanup, and local CLIP model prerequisites.
- [ ] 5.2 Clarify that the visualizer is an engineer inspection tool and update stale documentation without changing the existing CLI, video-input, results, progress, resume, or OpenAI behavior.
