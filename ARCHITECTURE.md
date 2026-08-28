# Frame Clarity Analyzer Architecture

## Status And Scope

This document defines the architecture for the current local prototyping phase
of Frame Clarity Analyzer. It describes the existing reliable analysis core and
the boundaries within which additional local engineer utilities may be added.

The current phase prioritizes:

- A simple local system interaction model.
- CLI-driven functionality.
- Fast, deterministic engineer feedback.
- End-to-end testing without hosted infrastructure.
- Privacy, reliability, and explicit failure behavior.

This document does not define or authorize a hosted batch-processing system. Cloud
workers, hosted APIs, databases, object storage, hosted identity, and cloud
retention workflows are deferred. They must be designed separately after the
product, privacy, operational, and cost requirements are defined.

`BUSINESS_CONTEXT.md` is authoritative for Wedding Glamour business facts and
policies. `PRODUCT_VISION.md` defines this repository's product direction. This
document describes technical boundaries and must not silently resolve business
open questions.

Architecture decisions are recorded in [`docs/adr/`](docs/adr/). Before planning,
reviewing, designing, or implementing a non-trivial feature or technical
boundary change, contributors and agents MUST inspect that directory and read
the ADRs relevant to the change. ADRs document accepted constraints, tradeoffs,
and revisit triggers; they are part of the technical context and must not be
silently contradicted. A deliberate change to an accepted decision should update
or supersede the relevant ADR in the same work.

The initial video extraction decision is recorded in
[`ADR-0001`](docs/adr/0001-use-ffmpeg-for-initial-video-extraction.md): use local
FFmpeg and ffprobe for the first video-input capability. This does not authorize
streaming, a Python runtime migration, or hosted operation.

## Product Boundary

The product turns a private set of pre-extracted video-frame images into a
ranked set of still-image candidates for human review.

The product is review-first:

- A score is a ranking aid, not an objective declaration of photographic truth.
- Every frame remains represented by an explicit outcome.
- Failed and skipped frames are visible and are not converted into fallback
  quality scores.
- The analyzer does not publish directly to a shared gallery.
- Gallery inclusion remains subject to the couple's ownership and approval or
  explicitly granted permissions defined by the broader Wedding Glamour product.

The current input boundary is a directory of numerically named PNG frames. Video
decoding, frame sampling, near-duplicate detection, and review-queue integration
are product expansion areas, not current-phase architecture components.

## Architecture Overview

```text
                         Engineer or automation
                                  |
                    python identify_clearest_frames.py
                                  |
                         CLI adapter (cli.py)
                                  |
                  +---------------+----------------+
                  |                                |
          Frame discovery                    Configuration
                  |                                |
                  +---------------+----------------+
                                  |
                   Immutable frame manifest
                                  |
                         Batch orchestration
                           (core.py)
                                  |
             +--------------------+--------------------+
             |                    |                    |
       Analyzer protocol   Progress store       Result/output handling
             |                    |                    |
      +------+-------+      Atomic JSON       +---------+----------+
      |              |      checkpoints       |                    |
   Local CLIP   Explicit                    Results JSON     Ranked copies
                OpenAI
             external path
```

The reusable workflow is independent of the presentation layer. The CLI is the
primary adapter today. Any local web utility must call the same workflow seams
and must not implement a second analysis path.

## Runtime Flow

1. The CLI parses options and validates numeric values before initializing a
   model or external client.
2. Discovery validates the input directory and frame naming contract.
3. Discovery creates an ordered immutable manifest containing frame identity and
   the deterministic input-set identity used for resume checks.
4. The CLI resolves progress, results, and optional copied-frame destinations.
5. The analyzer factory creates either the local CLIP adapter or the explicitly
   selected OpenAI adapter.
6. The batch orchestrator loads compatible progress, selects pending and failed
   frames, and invokes the analyzer protocol.
7. Each frame becomes exactly one persisted `success`, `failed`, or `skipped`
   outcome.
8. Progress is checkpointed at batch boundaries using atomic replacement.
9. Results are ranked deterministically and written as JSON.
10. Successful top-ranked frames are optionally copied for review or downstream
    local use.
11. The CLI emits human-readable or JSON output and returns an automation-safe
    exit status.

## Component Responsibilities

| Component | Responsibility | Boundary |
| --- | --- | --- |
| `identify_clearest_frames.py` | Compatibility executable entry point | Delegates to the CLI; contains no workflow policy |
| `frame_clarity.cli` | Argument parsing, configuration, presentation, and exit codes | Thin adapter over reusable functions |
| `frame_clarity.discovery` | Input validation, numeric ordering, content identity, and manifest creation | Accepts filesystem input; returns a validated manifest |
| `frame_clarity.models` | Dependency-light data contracts and outcome invariants | No model, network, or framework imports |
| `frame_clarity.core` | Batch scheduling, analyzer normalization, retries through reruns, and checkpoint coordination | Depends on protocols and stores, not concrete model SDKs |
| `frame_clarity.analyzers` | Analyzer protocol, score validation, local CLIP adapter, and optional OpenAI adapter | External SDKs are isolated behind the analyzer protocol |
| `frame_clarity.progress` | Versioned progress schema, strict loading, metadata matching, and legacy migration | Never treats corrupt or incompatible state as empty progress |
| `frame_clarity.storage` | Atomic JSON write and read primitives | Publishes complete files only |
| `frame_clarity.results` | Deterministic ranking, result serialization, and successful-frame copying | Failed and skipped outcomes are never copied as top results |
| `frame_clarity.errors` | Typed expected workflow errors | CLI converts them into concise diagnostics and nonzero status |

The dependency direction is intentionally one-way:

```text
CLI -> workflow core -> contracts/protocols
                       -> discovery
                       -> progress/storage
                       -> results/storage
                       -> analyzer protocol
                                      -> optional model/API SDKs
```

Core contracts must remain importable in an environment without model files,
credentials, network access, or GPU hardware.

## Interface And Data Contracts

### Frame Manifest

Discovery accepts PNG files whose stems match the configured, case-sensitive
prefix followed by a decimal frame number. It rejects missing, non-directory,
empty, malformed, and duplicate-number inputs.

The manifest is the canonical source for:

- Numeric processing order.
- Frame-to-result identity.
- Progress membership checks.
- Deterministic result order.
- Detection of changed input content.

### Analyzer Protocol

An analyzer accepts a frame path and returns an `AnalyzerResult` containing a
finite score from 0 through 100 and optional reasoning. The orchestrator owns
validation and status transitions. Analyzer-specific exceptions or malformed
responses become failed outcomes with sanitized diagnostics.

The local CLIP analyzer is the default privacy-preserving path. The OpenAI
adapter is an explicit external-processing path. External processing must not
be enabled accidentally by defaults, and provider/configuration suitability for
wedding imagery must be established before customer use.

### Outcome Model

Every discovered frame has one outcome:

- `success`: contains a validated score and optional reasoning.
- `failed`: contains a sanitized diagnostic, a null score, and attempt count.
- `skipped`: contains a reason, a null score, and is not treated as analysis
  success.

No caller may represent failure with a normal score. The result document retains
all outcomes, while ranking places successful frames first and unresolved frames
after them in deterministic frame order.

### Progress And Results

Progress records the input-set identity, analyzer, model, scoring version, and
per-frame outcomes. It is written through a same-directory temporary file and
atomic replacement. Resume reuses only compatible successful outcomes and
retries failed outcomes.

Results are written to JSON beside the input directory by default. Copied frames
are a derived local artifact and are never the source of truth for analysis
state.

## CLI As The Primary Interface

The supported engineer and automation interface is:

```text
python identify_clearest_frames.py [options]
```

The CLI must continue to provide:

- Explicit input, output, progress, and results paths.
- Analyzer selection and model configuration.
- Batch sizing and bounded concurrency controls.
- Resume and no-resume behavior.
- Human-readable and machine-readable output.
- Nonzero exit status for invalid inputs, configuration errors, persistence
  errors, unresolved frame failures, and interruptions.

The importable processing function remains useful for tests and local tools, but
it is not a promise of a separately packaged public library. Packaging, a stable
HTTP API, and service deployment are outside this phase.

## Local Web Utility Boundary

Limited local web utilities may be introduced for engineer control and testing.
They are optional presentation adapters, not a second product runtime.

They must:

- Reuse the same manifest, orchestration, analyzer, progress, and result
  components as the CLI.
- Bind to loopback by default and be clearly documented as local engineer tools.
- Expose only controls needed to start, inspect, test, or diagnose local runs.
- Reuse structured outcomes and exit-equivalent failure information.
- Support fixture or fake-analyzer modes for repeatable tests where appropriate.
- Avoid introducing a database, hosted session model, or new persistent state.
- Never imply that loopback access is a substitute for Wedding Glamour product
  authorization.

The first local web utility should be justified by a concrete engineer testing
need. It should not become a general review application during this phase.

## Security And Privacy

Wedding imagery and derived analysis data are sensitive. The architecture
follows these business constraints:

- Wedding data is private by default.
- Couples own event data and shared memories, including access, edits, sharing,
  deletion, and export controls as defined by the broader product.
- Shared-gallery content requires couple approval unless explicit permissions
  allow direct contribution.
- Company administrators should not have access to wedding data.
- Data and memories should be hard deleted after the defined post-payment
  retention period, currently up to 30 days.

The current local CLI does not enforce hosted identity, ownership, access,
retention, or deletion policy. Those controls are prerequisites for any future
customer-facing integration and must not be inferred from filesystem access.

Engineering controls for this phase include:

- Keep local processing as the default.
- Make every external model/provider choice explicit in configuration and
  user-facing operation.
- Keep API keys, raw image data, and sensitive provider details out of logs,
  progress files, result files, source control, and error messages.
- Prefer environment-based credentials over command-line secrets. The existing
  `--api-key` compatibility option should not be expanded or used in automation.
- Treat paths, symlinks, image files, model responses, and API responses as
  untrusted input.
- Define and enforce input size, count, and resource limits before accepting
  large or untrusted media sets.
- Review output-directory permissions and avoid writing artifacts into shared
  locations unintentionally.
- Require external model providers and configurations to meet applicable privacy
  guarantees, including restrictions on training use, before customer imagery is
  sent outside the local environment.

Known current-phase hardening gaps include symlink handling, resource limits,
concurrent-run coordination, provider timeout and cost budgets, and transactional
coordination between JSON results and copied frames. They are documented risks,
not reasons to weaken the existing explicit-failure contract.

## Reliability And Operability

The workflow is designed for repeatable local batches:

- Discovery creates a deterministic input identity.
- Processing order and tie-breaking are deterministic.
- Progress checkpoints preserve completed work across interruption.
- Atomic replacement preserves the previous valid JSON file when publication
  fails.
- Failed frames remain visible and can be retried on resume.
- Metadata mismatches prevent mixing results from different input or analyzer
  contexts.
- Invalid analyzer responses never receive fallback scores.
- Exit statuses distinguish automation success from unresolved work.

Operational behavior must remain diagnosable without exposing sensitive content:

- Diagnostics name the relevant local path or frame filename where safe.
- Failures identify status, attempts, and sanitized reason.
- Model/provider credentials and raw prompts containing sensitive details are not
  persisted.
- Progress and results remain human-readable JSON with stable ordering.

Future reliability work in this phase may address stale copied outputs, atomic
publication of derived artifacts, input mutation during a run, concurrent runs
using the same artifact paths, and safer retry classification for external API
errors. Such work must preserve deterministic reruns and visible failures.

## Testability Strategy

Feature boundaries are selected partly by whether an engineer can exercise them
without live infrastructure.

### Unit Tests

Pure or dependency-light behavior should be tested directly:

- Filename parsing and numeric ordering.
- Manifest identity.
- Score validation and CLIP score calculation.
- External response parsing.
- Outcome invariants and ranking.
- Progress schema validation and metadata comparison.
- Result serialization.

### Component Tests

Use temporary directories, local fixtures, fake analyzers, and mocks to test:

- Discovery diagnostics.
- Batch orchestration and completion-order independence.
- Failure retry and attempt counts.
- Atomic progress persistence and corruption handling.
- Legacy progress migration.
- Resume filtering and metadata mismatch.
- Result writing and successful-frame copying.
- Analyzer selection without initializing live providers.

### CLI Tests

Subprocess or CLI-adapter tests should cover:

- Help and compatibility invocation.
- Invalid numeric and analyzer options.
- Missing, empty, and malformed input directories.
- Explicit result and failure artifacts.
- Machine-readable output.
- Nonzero failure and interruption behavior.

### End-To-End Tests

The default end-to-end path begins at a fixture frame directory because video
ingestion is not in the current boundary:

```text
fixture PNG directory
        |
CLI invocation with fake/local test analyzer
        |
manifest -> batch run -> progress checkpoint
        |
results JSON + ranked copied frames + exit status
```

Required end-to-end scenarios include:

- A successful deterministic batch.
- A failed frame producing a visible failed result and nonzero exit status.
- An interrupted or partially completed batch resuming without reprocessing
  matching successful frames.
- A changed input or analyzer context being rejected.
- Stable ordering when analysis completion order differs.
- `--no-save` producing results without copied frames.
- Any local web utility invoking the same workflow and producing equivalent
  outcomes to the CLI.

Default verification must not require model downloads, API credentials, API
credits, network access, or GPU hardware. Optional CLIP/OpenAI smoke tests are
separate and must state their prerequisites.

## Change And Evolution Rules

### Architecture Decision Records

Before planning a feature or change that affects a technical boundary:

1. Inspect `docs/adr/` for relevant decisions.
2. Read applicable ADRs and identify constraints, consequences, and revisit
   triggers that affect the proposed work.
3. Preserve accepted decisions unless the change explicitly revises them.
4. Create or update an ADR when the work introduces a durable architectural
   decision, changes an accepted decision, or establishes a new cross-cutting
   constraint.
5. Reference the relevant ADR from proposals, designs, or implementation
   documentation when the decision materially affects the work.

Changes should preserve these stable boundaries:

- Input discovery and manifest identity.
- Analyzer protocol and score validation.
- Status-bearing outcomes.
- Progress metadata and resume semantics.
- Deterministic result ordering.
- CLI exit-status behavior.
- Offline testability of the core.

When a change affects a compatibility surface, update the README and relevant
OpenSpec requirements in the same change. New local interfaces should be added
only when they map to a clear engineer workflow and can be tested with local
fixtures or fakes.

Video extraction, deduplication, provenance expansion, review integration, and
hosted operation should be introduced as separate capability changes rather than
quietly added to the current analysis core.

## Deferred Decisions

The following remain outside this architecture document and must not be resolved
by implementation assumption:

- Eventual cloud worker and service topology.
- Supported video formats and extraction strategy.
- Processing-time, availability, and quality expectations.
- Cloud storage limits, cost model, and pricing.
- Hosted identity, authorization, and tenant isolation implementation.
- Review-queue interaction design.
- Download, sharing, print ordering, moderation, reporting, and contributor
  control policies.
- Exact video-feature success metrics.
- Final support for user-defined quality preferences.

These decisions require the appropriate product, business, privacy, and
technical-owner review before the system moves beyond local prototyping.
