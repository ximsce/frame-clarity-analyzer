## Why

Developers currently need to invoke the CLI and inspect generated files manually
to validate the complete video-to-frame pipeline and judge whether the selected
frames are useful. A narrow local visualizer will make this feedback loop faster
without turning the prototype into a hosted service or customer review product.

## What Changes

- Add a local browser-based engineer utility for processing one selected video
  and viewing its ranked frame candidates.
- Upload the selected file over loopback into an isolated, temporary run
  workspace.
- Run the existing video extraction and analysis workflow, using the local CLIP
  analyzer only.
- Default web runs to 5 FPS and offer bounded sampling choices through 30 FPS;
  preserve the CLI's existing 30 FPS default and its other behavior.
- Display run phase, analysis progress, ranked frame images, scores, source
  timestamps, reasoning, and visible failure diagnostics.
- Keep the utility single-run, ephemeral, local-only, and review-only. It will
  not publish, share, approve, reject, or persist gallery content.
- Document how to start the utility and clarify that it is not a hosted or
  customer-facing review interface.

## Capabilities

### New Capabilities

- `local-pipeline-visualizer`: Local CLIP-only web visualization of one video
  pipeline run and its ranked frame results.

### Modified Capabilities

None. The visualizer consumes the existing `video-input` and
`reliable-analysis-core` contracts without changing their requirements.

## Impact

- A new local web presentation adapter and its browser assets will be added
  without creating a database, hosted API, or packaging layer.
- The adapter will call the existing video extraction, manifest, analysis,
  progress, result, and copied-frame behavior rather than implementing a second
  pipeline.
- Tests will need local HTTP/job-flow coverage with fake media and analyzer
  boundaries; default verification must remain offline and must not download a
  CLIP model.
- The README and relevant local-development documentation will gain startup,
  scope, sampling, privacy, and cleanup guidance.
- Existing CLI invocation, numbered-PNG input behavior, output artifacts,
  progress semantics, resume behavior, and OpenAI analyzer support remain
  compatible and unchanged.
