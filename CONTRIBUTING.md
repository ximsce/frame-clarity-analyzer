# Contributing

## Project Principles

Keep this project small, explicit, and usable from the command line. Prefer a
focused change over a broad refactor, and preserve existing behavior unless the
change intentionally updates the CLI or its documented contracts.

Read [ARCHITECTURE.md](ARCHITECTURE.md) alongside `BUSINESS_CONTEXT.md` and
`PRODUCT_VISION.md` before changing workflow boundaries, persistence, analyzer
integration, or local engineer utilities.

Important compatibility surfaces include:

- frame filename parsing and numeric ordering;
- `FRAME_PREFIX` and CLI defaults;
- progress and result JSON files;
- resume behavior;
- `clip` versus `openai` analyzer selection; and
- rank-prefixed output filenames.

When changing one of these surfaces, update the README and the relevant OpenSpec
specification or change artifacts in the same work.

## OpenSpec Development

Use OpenSpec for work that changes behavior, adds a capability, or has meaningful
design tradeoffs. The repository is initialized for OpenCode and uses the
`spec-driven` schema.

The normal sequence is:

1. Use `/opsx-explore` to understand the current implementation and constraints.
2. Use `/opsx-propose "..."` to create a change proposal for non-trivial work.
3. Review the proposal, design, requirements, and task breakdown.
4. Use `/opsx-apply <change-name>` to implement the planned work.
5. Use `/opsx-sync <change-name>` when durable requirements need to update the
   main specs.
6. Use `/opsx-archive <change-name>` after implementation and verification are
   complete.

Project context for these operations is maintained in `openspec/config.yaml`.
Do not put temporary implementation notes there; put feature-specific details in
the active change directory.

## Code Changes

- Keep the CLI as the primary user interface.
- Use type annotations and small functions where they improve clarity.
- Keep API keys and image data out of logs, fixtures, and commits.
- Treat model output and filesystem input as untrusted data.
- Make retries, fallback scores, and resumability explicit in user-visible output.
- Avoid requiring a model download or live API call for unit tests.
- Update user-facing documentation whenever command behavior changes.

## Local Verification

Run the checks that apply to the change:

```bash
python3 -m py_compile identify_clearest_frames.py
python3 identify_clearest_frames.py --help
openspec doctor
openspec validate
```

If tests are added, run the project test command as well. A full analyzer run is
optional and may require model downloads, GPU support, OpenAI credentials, or API
credits. State those requirements clearly in the change summary.

## Data and Generated Files

Do not commit raw video frames, copied clear frames, API keys, progress files, or
analysis result files. The repository ignores the current generated JSON and
output directory, but verify `git status` before creating a commit.
