# reliable-analysis-core Specification

## Purpose

This capability provides a dependable contract for discovering numbered frames,
analyzing them, resuming interrupted work, and reporting automation-safe results.

## Requirements

### Requirement: Frame discovery validates the input set

The system SHALL discover PNG files in the requested frames directory using the
configured, case-sensitive frame prefix followed by a decimal frame number in
the filename stem. It SHALL order valid frames by numeric frame number, not
lexical filename order. A missing path, a path that is not a directory, an
empty directory, or a PNG filename that does not follow the input contract
SHALL produce a clear diagnostic identifying the path or filename and SHALL
prevent a successful run.

#### Scenario: Valid frames are numerically ordered

- **WHEN** the directory contains `rawFrames2.png`, `rawFrames10.png`, and `rawFrames100.png`
- **THEN** discovery returns them in the order 2, 10, 100

#### Scenario: Invalid PNG names are diagnosed

- **WHEN** the directory contains `rawFrames1.png` and `thumbnail.png`
- **THEN** the run reports `thumbnail.png` as an invalid frame filename instead of raising an uncontextualized parsing exception

#### Scenario: Missing or empty input is rejected

- **WHEN** the requested frames path does not exist, is not a directory, or contains no valid frame set
- **THEN** the CLI emits a diagnostic and exits with a nonzero status

### Requirement: Analyzer selection and scores are validated

The system SHALL support the existing `clip` and `openai` analyzer selections and
SHALL reject an unknown selection with a clear diagnostic. An accepted analyzer
result SHALL contain a finite numeric score from 0 through 100 inclusive and
optional reasoning. Missing, nonnumeric, nonfinite, or out-of-range scores SHALL
be treated as analysis failures rather than substituted with a default score.

#### Scenario: An invalid analyzer selection fails clearly

- **WHEN** the user selects an analyzer other than `clip` or `openai`
- **THEN** the CLI identifies the invalid value and exits with a nonzero status without processing frames

#### Scenario: An invalid external score becomes a failure

- **WHEN** an analyzer response contains no score, a nonnumeric score, `NaN`, or a score outside 0 through 100
- **THEN** the frame receives a failed outcome with an error detail and no score

#### Scenario: CLIP scoring remains bounded

- **WHEN** the local CLIP analyzer calculates a composite score
- **THEN** the accepted result is finite and bounded from 0 through 100 inclusive

### Requirement: Frame outcomes distinguish success, failure, and skip

Every discovered frame SHALL have exactly one persisted outcome of `success`,
`failed`, or `skipped`. A successful outcome SHALL have a validated score. A
failed outcome SHALL have a nonempty diagnostic and a null score, and SHALL
record the number of attempts. A skipped outcome SHALL have a reason and SHALL
NOT be treated as a successful analysis. Failures SHALL NOT be represented by a
normal score such as 50.0.

#### Scenario: Analyzer exception is visible as failure

- **WHEN** analysis raises an exception for a frame
- **THEN** the result records status `failed`, a sanitized error detail, a null score, and an incremented attempt count

#### Scenario: Successful result has a score

- **WHEN** analysis returns a valid score for a frame
- **THEN** the result records status `success` and that score

### Requirement: Ranking and batch processing are deterministic

The system SHALL retain one result for each discovered frame and SHALL serialize
results deterministically regardless of analyzer completion order. Successful
frames SHALL rank ahead of failed and skipped frames by descending score; ties
among successful frames SHALL be broken by ascending numeric frame number.
Failed and skipped frames SHALL retain deterministic numeric frame order after
successful frames and SHALL never be copied as top frames. Progress SHALL be
checkpointed after each configured batch boundary.

#### Scenario: Parallel completion does not change output order

- **WHEN** two analyzers complete frames in an order different from discovery
- **THEN** the serialized ranking and copied rank names remain the same as they would be for sequential completion

#### Scenario: Failed frames are excluded from copied top results

- **WHEN** a failed frame would otherwise appear within the requested top-N positions by a fallback score
- **THEN** it is omitted from copied outputs and remains a failed record in the full results

### Requirement: Progress is atomic and metadata-aware

The system SHALL write progress as versioned JSON containing the discovered
input set identity, analyzer selection, selected model, scoring-version
identity, and per-frame outcome data. A progress checkpoint SHALL be published
atomically so a process interruption cannot leave a partially written
valid-path file. Corrupt, unreadable, structurally invalid, or
metadata-incompatible progress SHALL produce a clear diagnostic and SHALL NOT be
silently treated as no progress.

#### Scenario: Interrupted checkpoint does not replace the last valid progress

- **WHEN** a process is interrupted while publishing a progress checkpoint
- **THEN** the previously published progress remains readable and complete

#### Scenario: Corrupt progress is reported

- **WHEN** the progress path contains malformed JSON or invalid progress structure
- **THEN** resume fails with a diagnostic naming the progress file rather than silently starting over

#### Scenario: Progress identifies its analysis context

- **WHEN** progress is written for a frame set and analyzer configuration
- **THEN** the progress includes enough input-set, analyzer, model, and scoring-version metadata to reject incompatible reuse

### Requirement: Resume behavior is safe and repeatable

When resume is enabled, the system SHALL reuse only successful results whose
progress metadata matches the current input set, analyzer, model, and scoring
version. Failed frames SHALL be eligible for retry, and a retry SHALL increment
their attempt count. A metadata mismatch SHALL be reported and SHALL require an
explicit no-resume invocation to discard the old context. Repeating a run with
unchanged inputs and successful progress SHALL not reanalyze completed
successful frames or change their serialized results.

#### Scenario: Failed frame is retried

- **WHEN** a previous checkpoint contains a failed frame and the user resumes with matching metadata
- **THEN** that frame is selected for analysis again while matching successful frames are reused

#### Scenario: Changed analyzer context is not mixed

- **WHEN** progress was created for one analyzer or model and the user resumes with another
- **THEN** the CLI reports a metadata mismatch and does not combine the two result contexts

#### Scenario: Resume is deterministic

- **WHEN** the same input set, configuration, and analyzer outcomes are run twice
- **THEN** the selected work, result ordering, statuses, and copied filenames are identical

### Requirement: Results and copied outputs preserve the existing contract

The system SHALL continue to write the full JSON results beside the input
directory at `frame_analysis_results.json` by default and progress at
`frame_analysis_progress.json` by default. The results SHALL include all frame
outcomes, status, score where applicable, reasoning where available, error
details for failures, and the configured top-N value. When copying is enabled,
successful top frames SHALL be copied to the configured output directory,
defaulting to the parent directory's `clearest_frames`, using the existing
numeric rank prefix.

#### Scenario: Default artifacts remain discoverable

- **WHEN** the command is run without custom progress, results, or output paths
- **THEN** it writes the progress and results files beside the frames directory and copies eligible top frames to the parent `clearest_frames` directory

#### Scenario: No-save suppresses copies only

- **WHEN** the user invokes the documented `--no-save` option
- **THEN** the JSON results are still generated and frame copies are not written

### Requirement: CLI compatibility and exit status are explicit

The system SHALL continue to support `python identify_clearest_frames.py` and the
documented command options and defaults unless a new option is explicitly
added. It SHALL validate positive batch size, top-N, worker count, and request
limit values, and nonnegative request delays, before analysis begins. It SHALL
return a zero exit status only when all discovered frames finish as successful
or explicitly skipped and required artifacts are written. Invalid arguments,
input errors, analyzer initialization failures, progress errors, unresolved
frame failures, output errors, and interruptions SHALL return nonzero exit
statuses.

#### Scenario: Documented script invocation remains available

- **WHEN** the user runs `python identify_clearest_frames.py --help`
- **THEN** the command succeeds and exposes the documented CLI interface

#### Scenario: Validation rejects unusable numeric options

- **WHEN** the user supplies a zero or negative batch size, top-N, worker count, or request limit, or a negative request delay
- **THEN** argument parsing reports the invalid value and exits nonzero before model or API initialization

#### Scenario: Unresolved analysis failure is automation-visible

- **WHEN** at least one discovered frame remains failed after the run
- **THEN** results and progress identify the failure and the CLI exits nonzero

### Requirement: Core behavior is testable without external services

The project SHALL provide tests for discovery, empty and missing directories,
progress save/load and corruption, resume filtering, score calculation, OpenAI
response parsing, output copying, analyzer selection, and CLI exit behavior
using fakes, fixtures, or mocks. Those tests SHALL NOT require model downloads,
GPU hardware, network access, API keys, API credits, or external services.

#### Scenario: Default test suite runs offline

- **WHEN** the core test command runs in an environment without model files, credentials, GPU hardware, or network access
- **THEN** the tests complete using local fixtures and do not attempt external service calls
