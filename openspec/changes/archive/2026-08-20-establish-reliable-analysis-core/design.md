## Context

The implementation is currently concentrated in
`identify_clearest_frames.py`. Discovery, two analyzer backends, progress JSON,
result reporting, copying, and argument parsing share mutable data and control
flow. The existing progress format has no analysis identity, writes directly to
the destination, and marks returned fallback scores as processed. See
`proposal.md` for the motivation and
`specs/reliable-analysis-core/spec.md` for the observable contract.

## Goals / Non-Goals

**Goals:**

- Create narrow Python-callable boundaries that can be exercised with local test
  doubles while preserving the script as the CLI adapter.
- Make outcome state, progress identity, retry selection, and exit status explicit
  at the orchestration boundary.
- Preserve current defaults and artifact locations while making generated JSON
  safe to consume by automation.
- Keep optional CLIP and OpenAI imports isolated from the core test path.

**Non-Goals:**

- Adding video decoding, deduplication, a plugin registry, packaging, or a service
  layer.
- Changing the scoring heuristic or the user-facing analyzer prompts beyond the
  validation needed to reject unusable responses.
- Making model-backed integration tests part of the default test command.

## Decisions

### Layer the workflow around explicit data contracts

Introduce focused boundaries for discovery, analyzer selection/protocol, result
outcomes, batch orchestration, progress storage, result serialization, copying,
and CLI adaptation. The analyzer protocol accepts a frame path and returns a
candidate score/reasoning value; the orchestration layer validates it and owns
status transitions. This keeps backend-specific failures from being mistaken for
successful results and lets tests provide a deterministic fake analyzer.

An alternative was to keep the single script and add more conditionals. That has
lower file churn but preserves the current coupling and makes offline tests depend
on optional imports, so it is rejected.

### Use a canonical frame manifest for identity and ordering

Discovery produces a canonical manifest containing each frame's normalized name,
numeric index, and file identity metadata. The manifest is sorted by numeric index
and is used for analysis selection, result ordering, and progress comparison. The
input-set identity is a deterministic digest of the ordered names and file
content/metadata needed to detect changed inputs; analyzer name, model name, and a
constant scoring-version identifier are stored separately in the progress
metadata. Duplicate numeric indices or duplicate names are rejected rather than
assigned an arbitrary order.

The alternative of identifying progress only by filename would preserve more old
state but could reuse a score after a frame was replaced. The manifest identity
favors correctness; users can explicitly use `--no-resume` when they intend to
start a new context.

### Model outcomes as status-bearing records

Replace score-only records with a result model containing frame identity, status,
nullable score, reasoning, error detail, and attempt count. A backend exception,
invalid score, unreadable image, or invalid API response transitions the frame to
`failed`; it never creates a fallback score. Only successful records participate
in ranking and copying. Explicit skips remain visible and are not silently
converted to success.

### Make progress publication atomic and conservative

The progress writer serializes a versioned document to a temporary file in the
same directory, flushes it, and replaces the destination atomically. The
orchestrator writes only after a completed batch and does not expose partially
collected parallel results. Loading validates JSON shape, schema version, frame
membership, statuses, scores, and metadata before returning state. Corrupt files
raise a user-facing progress error instead of being interpreted as an empty run.

Legacy documents containing `processed_frames` and `scores` are accepted through
a narrow migration reader. Entries must match discovered filenames and contain
finite scores in range; they are imported as historical successful outcomes and
immediately rewritten in the new versioned format. Legacy state cannot identify
the old analyzer or scoring version, so it is never combined with a new explicit
metadata context after migration. `--no-resume` remains the escape hatch for
rerunning all frames.

### Separate ranking from result storage

The full results document contains every discovered outcome. Ranking is a derived
view: successful scores descending with numeric frame index as the tie-breaker,
followed by failed and skipped records in manifest order. The top-N copy operation
consumes only the successful portion and retains the existing rank-prefixed
filenames. Result serialization should use stable key/record ordering and an
atomic replacement strategy matching progress publication where practical.

### Keep the CLI as a thin, explicit exit-code adapter

Argument parsing validates numeric constraints before backend initialization.
`main()` converts typed workflow errors into concise stderr diagnostics and
nonzero codes, while preserving `--help`, documented defaults, and
`python identify_clearest_frames.py`. The reusable processing function returns a
structured run result or raises typed errors; it does not print-and-return-success
for failures. API keys and sensitive backend details are excluded from error
messages and persisted records.

### Test through local seams, not real backends

Core tests use temporary directories, small PNG fixtures where image decoding is
needed, fake analyzers, deterministic responses, and monkeypatched filesystem or
clock operations for atomic-write cases. CLIP score math and OpenAI response
parsing are tested as pure functions. Optional backend smoke tests remain separate
and are marked as requiring dependencies, model files, hardware, credentials, or
network access.

## Risks / Trade-offs

- [Risk] Hashing or stat-ing every input frame adds startup I/O. -> Mitigation:
  compute the manifest once per run, reuse it for progress and ordering, and
  prefer metadata checks when the implementation can prove they detect changes.
- [Risk] Strict metadata matching makes stale progress unusable after a file set
  or model change. -> Mitigation: report the exact mismatch and retain the
  explicit `--no-resume` path; never silently mix contexts.
- [Risk] Legacy progress cannot distinguish an old real score from the old
  failure fallback of 50.0. -> Mitigation: migrate only structurally valid,
  in-range entries, document the limitation, and make all newly produced failures
  explicit and retryable.
- [Risk] Atomic replacement can fail because of permissions or filesystem
  limitations. -> Mitigation: surface the destination and OS error, preserve the
  previous file, and return a nonzero CLI status.
- [Risk] Parallel OpenAI calls can expose shared rate-limit state to races. ->
  Mitigation: centralize request pacing behind a synchronized boundary or force
  a safe sequential path when the backend cannot guarantee thread safety; cover
  the chosen behavior with deterministic tests.
