## 1. Define Video Contracts

- [x] 1.1 Add dependency-light source and frame provenance contracts for source identity, stream identity, requested/actual timestamps, sampling settings, and extractor identity.
- [x] 1.2 Extend frame manifest and outcome serialization to carry optional video provenance while preserving the existing numbered-PNG result shape.
- [x] 1.3 Include extraction context in video input identity and progress metadata so changed video or extraction settings cannot reuse incompatible analysis outcomes.

## 2. Implement FFmpeg Extraction

- [x] 2.1 Add an injectable FFprobe/FFmpeg runner boundary that resolves executables, invokes argument lists without a shell, disables interactive input, bounds diagnostics, and translates process failures into typed workflow errors.
- [x] 2.2 Parse probe output to validate a readable local file, select a usable video stream, determine presentation duration, and reject unknown or greater-than-180-second durations before extraction.
- [x] 2.3 Build the deterministic 30 FPS sampling plan and extraction command, including explicit stream selection, orientation handling, and RGB-compatible numbered PNG output.
- [x] 2.4 Implement isolated temporary extraction workspaces, output validation, extraction metadata, atomic completion publication, and cleanup or isolation of failed/interrupted extraction attempts.
- [x] 2.5 Implement reuse of only complete extraction artifacts whose source identity and extraction configuration match the current request; ensure mismatches trigger a fresh artifact-level extraction.

## 3. Integrate The CLI Workflow

- [x] 3.1 Add the explicit video input option and source mutual-exclusion validation without changing existing `--frames-dir` defaults or compatibility invocation behavior.
- [x] 3.2 Add video extraction, analysis, result, progress, and output path resolution while continuing to route extracted frames through the existing analysis core.
- [x] 3.3 Ensure preflight and extraction failures prevent analyzer initialization and produce concise diagnostics with nonzero exit statuses.
- [x] 3.4 Preserve existing analyzer selection, batch-size semantics, resume/no-resume behavior, `--no-save` behavior, deterministic ranking, and rank-prefixed copied-frame names for both input modes.

## 4. Persist Provenance And Results

- [x] 4.1 Attach per-frame video provenance to analysis outcomes and persist it in progress and results JSON without exposing credentials or unnecessary absolute paths.
- [x] 4.2 Preserve requested source timestamps and actual decoded timestamps when available, together with source stream and extraction context.
- [x] 4.3 Validate that complete extraction metadata and all required frame artifacts exist before analysis begins, and keep extraction failures distinct from frame analysis failures.
- [x] 4.4 Update result and progress tests to confirm directory-mode compatibility and strict rejection of mismatched video extraction contexts.

## 5. Add Automated Coverage

- [x] 5.1 Add unit tests for probe parsing, duration limits, stream validation, sampling-plan determinism, provenance serialization, and error sanitization.
- [x] 5.2 Add component tests with fake media runners for command construction, missing tools, nonzero exits, timeouts, malformed output, isolated workspaces, reuse, and artifact-level restart.
- [x] 5.3 Add CLI tests for video/frame input selection, preflight failures, custom artifact paths, nonzero exit behavior, and unchanged numbered-PNG compatibility.
- [x] 5.4 Add optional real-FFmpeg fixture tests for a short video, a three-minute boundary case, a rejected longer video, and a decoder failure; do not commit generated media or require these tests in the default offline suite.

## 6. Document And Verify

- [x] 6.1 Update README with FFmpeg/ffprobe prerequisites, video CLI usage, 30 FPS default, 180-second limit, extraction artifacts, restart behavior, provenance, and known storage implications.
- [x] 6.2 Update any user-facing help text and module documentation to distinguish local video processing from phone integration or hosted upload behavior.
- [x] 6.3 Run the default offline test suite, syntax compilation, CLI help smoke test, `openspec doctor`, `openspec validate`, and `git diff --check`.
- [x] 6.4 Run optional real-FFmpeg integration checks when the local prerequisite and fixture tooling are available; document that model downloads, credentials, GPU hardware, and network access remain unnecessary for the default checks.
