## Why

Frame Clarity Analyzer currently requires users to pre-extract numbered PNG
frames before analysis. This prevents the CLI from processing the phone-captured
video files that are the intended product input and leaves extraction,
timestamping, and source provenance outside the reliable workflow.

## What Changes

- Add a local CLI video-input mode alongside the existing `--frames-dir` mode.
- Validate video inputs with `ffprobe` and extract frames with `ffmpeg`.
- Use a default sampling density of 30 frames per second.
- Reject videos longer than three minutes before extraction begins.
- Extract into an isolated, deterministic numbered-PNG workspace that can feed
  the existing frame-analysis core.
- Add artifact-level extraction restart: completed matching extractions may be
  reused, while interrupted or failed temporary extractions are discarded and
  restarted from the beginning.
- Persist extraction identity, sampling settings, source stream information,
  and source timestamps/provenance in the first results JSON.
- Preserve explicit extraction, analysis, and persistence failures with
  automation-safe nonzero exit statuses.
- Document FFmpeg and ffprobe as local macOS/Linux prerequisites.
- Preserve the existing numbered-PNG input mode, analyzer selections, progress
  behavior, result ranking, and copied-frame naming behavior.

## Capabilities

### New Capabilities

- `video-input`: Accept, validate, sample, extract, and prepare local video files
  for analysis with bounded duration, deterministic artifacts, restart-safe
  extraction, and source provenance.

### Modified Capabilities

- `reliable-analysis-core`: Extend the result contract additively so analyzed
  frames originating from video can include source identity, timestamps, and
  extraction provenance without weakening existing outcome, ranking, progress,
  or compatibility guarantees.

## Impact

- Affected CLI parsing and workflow orchestration in `frame_clarity.cli`.
- New FFmpeg/ffprobe process integration and extraction-state persistence.
- New or extended data contracts for extracted-frame metadata and result
  provenance.
- Existing discovery, analysis, progress, and result layers must continue to
  support pre-extracted PNG directories unchanged.
- `requirements.txt` remains Python 3.9-compatible; PyAV, streaming, and a
  Python runtime upgrade are not introduced.
- README and OpenSpec requirements will document the new CLI mode, FFmpeg
  prerequisite, three-minute limit, 30 FPS default, artifacts, and provenance.
- No hosted services, database, identity, authorization, gallery publication,
  direct phone integration, deduplication, or adaptive scene selection are
  introduced.
