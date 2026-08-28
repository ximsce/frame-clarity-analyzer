## Context

See `proposal.md` for the motivation and scope. The current workflow begins at
`frame_clarity.discovery.discover_frames`, which creates a complete immutable
PNG `FrameManifest`; `frame_clarity.core.run_analysis` then analyzes paths and
checkpoints outcomes through `ProgressStore`. The current result model has no
video source or timestamp fields.

This design follows
[`docs/adr/0001`](../../../docs/adr/0001-use-ffmpeg-for-initial-video-extraction.md).
The prototype remains CLI-first, local, Python 3.9-compatible, and
non-streaming. Existing numbered-PNG processing is a compatibility surface and
must continue to use the current workflow.

## Goals / Non-Goals

**Goals:**

- Add a video source path that produces the same kind of complete frame
  manifest consumed by the existing analysis core.
- Validate video duration and stream usability before expensive extraction or
  model initialization.
- Make extraction deterministic at a default 30 frames per second and cap it at
  180 seconds.
- Make incomplete extraction artifacts impossible to mistake for a complete
  analysis input.
- Preserve source timestamps and extraction context in results without exposing
  unnecessary local path details.
- Keep FFmpeg process behavior injectable and testable without model downloads,
  network access, or a live OpenAI client.

**Non-Goals:**

- Streaming decode, in-memory model batching, or PyAV integration.
- Direct mobile-device integration or hosted upload processing.
- Adaptive sampling, scene detection, near-duplicate selection, or quality-model
  changes.
- A database, review UI, identity layer, gallery publication, or new retention
  policy.

## Decisions

### Preserve the two input modes

Add an explicit video input mode while leaving the existing frame-directory mode
unchanged. The CLI should reject an invocation that supplies both sources. When
neither source is supplied, existing `--frames-dir` default behavior remains
unchanged.

The video path should be handled by a reusable local workflow function rather
than embedding extraction policy in the compatibility executable. This keeps
the current CLI adapter and analysis core as the only analysis path.

### Use an FFmpeg subprocess boundary

Use `ffprobe` with machine-readable output to inspect the local file, identify a
usable video stream, read duration and stream metadata, and establish source
context. Use `ffmpeg` with an argument list and no shell interpolation to create
the sampled PNG frame set.

The extractor should resolve or validate the configured executable paths before
running. It should capture bounded stderr for diagnostics, disable interactive
stdin behavior, enforce a process timeout, and translate missing executables,
nonzero exits, timeouts, and malformed probe output into typed workflow errors.

FFmpeg is preferred over OpenCV because codec and timestamp behavior are more
consistent for local phone video, and over PyAV because this prototype does not
need a Python runtime migration or an in-memory frame contract. See ADR-0001
for the complete decision and revisit triggers.

### Treat 30 FPS as a time-based sampling plan

The extractor uses a target sampling density of 30 frames per second, represented
by a deterministic sample plan tied to the probed presentation duration. Frame
identity is an ordinal sample identity, not an assumption that source frame
numbers or nominal source FPS are stable.

The extraction metadata should retain the target sampling rate and the requested
source timestamp for each sample. When the extraction path can obtain an actual
decoded presentation timestamp, it should retain that value as well. Orientation
handling and conversion to the existing RGB-compatible PNG input should be
explicit and deterministic.

The three-minute duration limit implies a maximum of 5,400 target samples before
any future additional limits. Extraction must validate its produced frame set
against the sampling plan rather than silently accepting an arbitrary partial
sequence.

### Use a persistent, isolated extraction workspace

Video processing gets a dedicated extraction workspace that is not scanned
together with unrelated PNG files. The workspace contains:

- numbered PNG frames using the configured frame prefix;
- an extraction manifest containing source identity, sampling configuration,
  stream metadata, and per-frame timestamp/provenance data; and
- a completion marker or equivalent metadata state that distinguishes a fully
  validated extraction from temporary work.

The default location should be derived from the video input and remain
overridable by an explicit extraction-directory option. Existing result,
progress, and copied-frame defaults should be derived consistently from the
final frame workspace unless the user supplies explicit paths.

### Restart extraction at artifact boundaries

The extractor writes into a unique temporary sibling workspace. It validates the
probe context, expected output sequence, readable PNG artifacts, and extraction
manifest before publishing the workspace as complete.

On interruption, process failure, invalid output, or publication failure, the
temporary workspace is not analyzed. A later run removes or ignores that
temporary state and starts extraction from the beginning. A complete workspace
is reusable only when source identity and all extraction settings match.

This deliberately does not checkpoint individual frames or decoder offsets.
Analysis progress remains a separate atomic JSON concern and can resume only
after a complete extraction is available.

### Extend frame contracts additively with provenance

Add an optional structured provenance value to the dependency-light frame
contract and serialize it into `FrameOutcome` records. Existing directory-mode
frames have no provenance value and retain their current JSON shape and behavior.

Video provenance should include at least:

- stable source-video identity and a safe source filename or identifier;
- selected source stream identity and relevant stream context;
- requested source timestamp and actual decoded timestamp when available; and
- extraction sampling configuration and implementation identity.

The extraction context must participate in the video manifest/progress identity
so changing the source or extraction settings cannot reuse unrelated analysis
outcomes. Provenance must be sanitized and must not contain credentials or an
unnecessary absolute local path.

### Keep analysis sequencing and progress semantics

After extraction is complete, the existing discovery and analysis orchestration
continues to own frame ordering, score validation, retries, checkpointing, and
exit status. The video workflow supplies a complete manifest and provenance
mapping; it does not create a second analyzer implementation.

Extraction failures prevent analysis from starting. Analyzer failures remain
per-frame failed outcomes with null scores. Required extraction or result
artifacts that cannot be written produce a nonzero CLI result. Existing failed
and skipped outcome invariants remain unchanged.

### Test the process boundary with fakes and optional media fixtures

The default suite should inject fake probe and extraction runners to test command
construction, probe parsing, duration rejection, output validation, temporary
workspace handling, reuse, restart behavior, provenance mapping, and failure
translation. Existing fake analyzers continue to cover analysis without model
downloads or credentials.

Small real-video integration tests may be optional when FFmpeg is installed.
They should use generated or temporary fixtures, avoid committing media, and
cover at least a normal short clip, a duration-limit failure, and a decoder
failure. The default test suite must not require FFmpeg if the test doubles can
exercise the behavior without it.

## Risks / Trade-offs

- [Risk] A 30 FPS target can produce up to 5,400 PNGs for one allowed video and
  consume significant disk and analysis time. -> Mitigation: enforce the
  180-second limit, validate output counts, keep extraction isolated, and make
  future resource limits explicit rather than silently dropping frames.

- [Risk] System FFmpeg builds differ in codec support and conversion behavior. ->
  Mitigation: probe before extraction, report tool failures clearly, record the
  tool identity in extraction metadata, and test representative phone formats
  on supported macOS and Linux environments.

- [Risk] Variable frame rate, nonzero start times, rotation, and source time
  bases can make timestamps ambiguous. -> Mitigation: use probe metadata and a
  time-based plan, retain requested timestamps plus actual timestamps when
  available, and never infer source time solely from nominal source frame rate.

- [Risk] A partial or stale workspace could contaminate a later run. ->
  Mitigation: use isolated temporary workspaces, atomic completion publication,
  strict source/settings identity matching, and validate every frame before
  analysis.

- [Risk] A subprocess can hang or emit sensitive/unbounded diagnostics. ->
  Mitigation: use argv-based invocation, disable stdin, enforce timeouts, bound
  captured output, and sanitize errors before persisting or displaying them.

- [Risk] Adding provenance to progress and result records can affect serialized
  output. -> Mitigation: make the field additive and optional, retain the current
  directory-mode shape, update documentation and tests, and reject incompatible
  video extraction contexts rather than mixing them.

## Migration Plan

1. Implement the video workflow and CLI option without changing existing
   frame-directory defaults or generated artifact names.
2. Add the extraction manifest and provenance-aware result serialization.
3. Test both input modes, including existing progress and legacy frame behavior.
4. Document FFmpeg/ffprobe installation, the 30 FPS default, the 180-second
   limit, extraction artifacts, restart semantics, and provenance fields.
5. If the video path must be rolled back, remove or disable only video-mode
   handling. Existing numbered-PNG analysis and its progress/results files remain
   usable.
