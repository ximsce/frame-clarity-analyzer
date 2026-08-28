# ADR-0001: Use FFmpeg for Initial Video Extraction

- Status: Accepted
- Date: 2026-08-27

## Context

Frame Clarity Analyzer is expanding from a local CLI that analyzes numbered PNG
frames to a local video input boundary. The likely source material is video
captured on phones, including common MOV/MP4 files, H.264 or HEVC video, variable
frame rate, and orientation metadata.

The current architecture is Python 3.9+ and keeps the analysis core separated
from filesystem discovery, progress persistence, and model adapters. The current
analyzer accepts image paths, and the current progress model assumes an immutable
frame manifest. The prototype does not have a packaging layer, hosted service,
database, or phone integration.

The extraction tool must run locally on macOS and Linux, preserve privacy by
default, provide clear failures, and support a deterministic and resumable
workflow. The choice should not prematurely introduce streaming, a Python
runtime migration, or a new native Python media binding.

## Decision

Use the FFmpeg command-line tools as the initial local video extraction backend:

- Use `ffprobe` for input validation and machine-readable stream and timing
  metadata.
- Use `ffmpeg` to decode and extract sampled frames.
- Treat FFmpeg and ffprobe as explicit local prerequisites and fail clearly when
  they are unavailable or unusable.
- Invoke the tools without shell interpolation, with bounded diagnostics,
  timeouts, and resource limits appropriate for untrusted media.
- Extract into an isolated workspace using deterministic numbered PNG names so
  the existing frame-analysis core can be reused.
- Keep extraction progress and identity separate from analysis progress while
  preserving atomic publication and strict metadata matching.
- Use a deterministic, time-based sampling policy rather than assuming nominal
  frame rate is sufficient for phone video.
- Retain source identity, stream information, requested and actual timestamps
  where available, and extraction configuration in extraction metadata or a
  sidecar manifest.
- Preserve the existing numbered-PNG input mode and its CLI behavior.

This decision is for the initial local prototype. It does not define the final
hosted architecture or resolve business policies concerning storage, retention,
permissions, downloads, or gallery publication.

## Alternatives Considered

### PyAV

PyAV provides direct access to FFmpeg libraries, decoded frames, PTS values, time
bases, and stream metadata. It may become preferable for a future streaming or
in-memory analysis pipeline.

It is not selected initially because current PyAV releases require Python 3.11+
while the repository supports Python 3.9+, and because its main performance
benefits require changing the path-based analyzer boundary. It also introduces a
large native dependency and a platform-specific wheel or source-build matrix.

### OpenCV

OpenCV provides a convenient `VideoCapture` API, but codec support, seeking,
timestamps, orientation handling, and backend behavior vary between macOS and
Linux. It is not sufficiently predictable as the provenance boundary for phone
video.

### Other wrappers and platform APIs

Libraries such as `ffmpeg-python`, MoviePy, and ImageIO do not remove the core
FFmpeg deployment and sampling decisions. AVFoundation and GStreamer are
powerful but do not provide the same straightforward cross-platform prototype
boundary.

## Consequences

### Benefits

- Broad practical support for common phone video formats and codecs.
- Strong alignment with the existing CLI-first local architecture.
- No Python-version migration is required for video extraction.
- Process isolation makes cancellation, timeout, and resource handling explicit.
- `ffprobe` provides a stable basis for validation and future provenance.
- The existing path-based analyzer and frame manifest can remain reusable.

### Costs and Risks

- Users must install compatible FFmpeg tools separately.
- FFmpeg builds can differ in codec availability, behavior, and version.
- Sampling, timestamp association, and true extraction resume require deliberate
  implementation; FFmpeg does not supply those product policies automatically.
- Materializing PNGs can consume substantial disk space for long or high-
  resolution videos.
- The initial design will not receive the full memory and throughput benefits of
  a streaming, in-memory pipeline.

## Explicit Non-Goals

This decision does not include:

- Direct phone or mobile-device integration.
- A Python 3.11+ migration solely to enable PyAV.
- A streaming decoder/analyzer pipeline.
- Near-duplicate detection or adaptive scene selection.
- A review UI, hosted worker, database, identity, or gallery publishing path.

## Revisit Triggers

Reconsider this decision if one or more of the following become concrete
requirements:

- The prototype needs to stream decoded frames directly into model microbatches.
- Exact frame-level PTS handling cannot be implemented reliably at the CLI
  boundary.
- Intermediate frame storage becomes a material performance, disk, or cost
  constraint.
- A self-contained Python installation is required instead of a system FFmpeg
  prerequisite.
- The project establishes a Python 3.11+ support policy and accepts the native
  dependency and platform support obligations of PyAV.

Any replacement should be recorded in a new ADR or an explicitly superseding
ADR, rather than silently changing this decision.
