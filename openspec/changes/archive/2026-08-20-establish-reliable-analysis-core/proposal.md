## Why

The current executable combines frame discovery, analysis, persistence, reporting,
copying, and CLI handling, so failures can be reported as ordinary scores and
resume state can silently become unsafe. The project needs a stable, testable
reliability baseline before adding broader functionality, without requiring model
downloads, GPU access, API keys, or a new invocation style.

## What Changes

- Extract testable boundaries for frame discovery, analyzers, result models, batch
  orchestration, progress persistence, result serialization, output copying, and
  CLI adaptation while keeping the existing script usable.
- Validate PNG frame names and report invalid filenames as actionable diagnostics;
  preserve numeric ordering for the existing prefix-plus-integer naming contract.
- Represent analysis outcomes explicitly as `success`, `failed`, or `skipped`.
  Failed outcomes carry error details and attempt counts and do not receive a
  fabricated score.
- Make progress persistence atomic and metadata-aware, including the input set,
  analyzer, model, scoring version, and per-frame status needed for deterministic
  resume decisions.
- Retry failed frames on resume by default, while retaining successful results
  and preserving deterministic ordering and serialization.
- Validate analyzer responses and score ranges before accepting results.
- Return nonzero exit codes for invalid input, unusable progress, analysis
  failures, and other CLI failures; retain the documented command and basic JSON
  result/output behavior.
- Add a dependency-light test suite for parsing, orchestration, persistence,
  resume, scoring, response parsing, copying, and analyzer selection.

Explicit non-goals are video extraction, deduplication, a plugin registry,
packaging/distribution work, and redesigning the documented CLI beyond the
reliability changes required here.

Compatibility decisions:

- `python identify_clearest_frames.py` remains supported, with its current
  documented defaults and basic output locations preserved.
- Existing valid legacy progress files may be imported as read-only input when
  their frame entries can be matched safely; newly written progress uses the
  versioned metadata-aware format. Corrupt, ambiguous, or mismatched progress
  fails loudly rather than being silently ignored.
- Results remain JSON and continue to be written beside the input directory by
  default; failed records use an explicit status and null score rather than the
  previous success-looking fallback score.
- A run is successful for automation only when all discovered frames are in a
  successful or explicitly skipped state. Any unresolved failure causes a
  nonzero exit status.

## Capabilities

### New Capabilities

- `reliable-analysis-core`: Defines validated frame discovery, analyzer result
  semantics, deterministic batch processing, safe progress/resume behavior,
  result and copied-output contracts, and CLI exit behavior.

### Modified Capabilities

None. `openspec/specs/` currently contains no existing capability requirements.

## Impact

- The main `identify_clearest_frames.py` workflow and its public CLI invocation.
- New or extracted Python modules and data models for discovery, analysis,
  orchestration, persistence, serialization, copying, and CLI adaptation.
- Progress and result JSON schemas, including compatibility handling for existing
  progress files and explicit failure records.
- Tests and development dependencies, but no requirement for external services in
  the default test suite. Optional CLIP/OpenAI integrations remain available for
  real analysis and are not needed by core tests.
