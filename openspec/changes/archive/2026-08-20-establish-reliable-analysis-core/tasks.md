## 1. Establish Core Contracts

- [x] 1.1 Define the frame manifest, analyzer protocol, status-bearing result model, typed workflow errors, and scoring-version identifier in reusable Python modules without importing optional model/API dependencies.
- [x] 1.2 Add the offline test harness, temporary-directory fixtures, fake analyzers, and minimal PNG fixtures needed to exercise the reusable core.

## 2. Implement Discovery and Analyzer Boundaries

- [x] 2.1 Implement prefix-plus-integer PNG discovery with numeric ordering, duplicate detection, input-set diagnostics, and deterministic manifest identity.
- [x] 2.2 Extract CLIP score calculation behind the analyzer protocol while preserving its existing 0-100 heuristic and isolating optional CLIP imports.
- [x] 2.3 Extract OpenAI response parsing and request handling behind the analyzer protocol, strictly validate finite 0-100 scores, and protect shared rate-limit state when concurrency is enabled.
- [x] 2.4 Implement analyzer selection and initialization errors with concise, non-secret diagnostics and no dependency on live services in core tests.

## 3. Implement Outcome and Batch Semantics

- [x] 3.1 Implement success, failed, and skipped result transitions with nullable scores, sanitized error details, and attempt counts; ensure backend exceptions and invalid responses never create fallback scores.
- [x] 3.2 Implement deterministic batch orchestration that preserves manifest identity, checkpoints at batch boundaries, ranks successful results by score and numeric frame index, and excludes failed/skipped records from copies.
- [x] 3.3 Add tests for score bounds, CLIP calculation, OpenAI JSON/code-block response parsing, analyzer selection, exception-to-failure conversion, retry attempts, tie ordering, and completion-order independence.

## 4. Implement Progress and Resume

- [x] 4.1 Define and validate the versioned progress document containing input-set, analyzer, model, scoring-version, and per-frame outcome metadata.
- [x] 4.2 Write progress through a same-directory temporary file, flush and atomically replace the destination, and preserve the last valid file when publication fails or is interrupted.
- [x] 4.3 Load progress strictly, report malformed or incompatible files, and migrate structurally valid legacy `processed_frames`/`scores` entries without silently accepting ambiguous data.
- [x] 4.4 Implement deterministic resume filtering that reuses only matching successful outcomes, retries failed outcomes, increments attempts, and requires explicit no-resume for metadata mismatches.
- [x] 4.5 Add tests for progress save/load, atomic publication, corruption diagnostics, metadata mismatch, legacy migration, success reuse, failed-frame retry, and deterministic repeated resume.

## 5. Implement Results and Output Handling

- [x] 5.1 Serialize the full deterministic result document with all statuses, nullable scores, reasoning, error details, and top-N metadata at the existing default location.
- [x] 5.2 Preserve default and custom output-directory behavior, copy only successful top-N frames with the existing numeric rank prefix, and keep `--no-save` limited to suppressing copies.
- [x] 5.3 Add tests for result serialization, failed-result representation, output copying, missing-source/output errors, and no-save behavior.

## 6. Preserve and Harden the CLI

- [x] 6.1 Convert `identify_clearest_frames.py` into a thin adapter over the reusable core while preserving `python identify_clearest_frames.py`, documented commands, defaults, analyzer options, and basic output locations.
- [x] 6.2 Add CLI validation for batch size, top-N, worker count, request limits, delays, paths, and analyzer selection before model/API initialization.
- [x] 6.3 Return explicit nonzero exit codes for invalid arguments, input/progress/analyzer/output errors, unresolved frame failures, and interruptions; keep successful `--help` behavior.
- [x] 6.4 Document the new status fields, retry/resume rules, metadata mismatch behavior, progress/result paths, and automation success criteria without expanding the project into packaging or service work.
- [x] 6.5 Add subprocess or CLI-adapter tests covering help, invalid filenames, missing/empty directories, invalid numeric options, analyzer failures, nonzero failure exits, and documented invocation compatibility.

## 7. Verification

- [x] 7.1 Run the dependency-light test command with network access, API credentials, model files, and GPU availability not required; confirm all core tests use local fixtures or mocks.
- [x] 7.2 Run `python3 -m py_compile identify_clearest_frames.py` and `python3 identify_clearest_frames.py --help` as CLI smoke checks.
- [x] 7.3 Run OpenSpec validation for the change and confirm generated frame images, progress files, result files, API keys, and other runtime artifacts are not included in the change.
- [x] 7.4 Record optional CLIP/OpenAI smoke tests separately, including their dependency, model-download, hardware, credential, and network prerequisites; do not make them part of the default test command.
