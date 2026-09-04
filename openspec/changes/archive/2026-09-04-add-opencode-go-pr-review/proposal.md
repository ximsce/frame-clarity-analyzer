## Why

Pull requests currently have no automated review workflow, so defects, security
risks, and missing tests must be identified entirely through human review. A
lightweight advisory review on pull-request creation would provide an additional
early signal while preserving human ownership of merge decisions.

The workflow should use the existing OpenCode Go subscription rather than adding
a second model-provider subscription or coupling review automation to the
frame-analysis runtime.

## What Changes

- Add a GitHub Actions workflow that runs when a pull request is opened.
- Fetch the pull-request diff through GitHub's API and send a bounded, text-only
  review request to an OpenCode Go API endpoint.
- Make the OpenCode Go model configurable without changing workflow logic or
  project code, with a documented default model.
- Store the OpenCode Go API key in GitHub Actions secrets and ensure it is never
  written to the repository, logs, artifacts, comments, or generated files.
- Validate the model response and post a concise advisory review comment to the
  pull request.
- Apply least-privilege GitHub token permissions and avoid executing
  pull-request-controlled code in the credentialed review job.
- Document provider configuration, usage limits, privacy considerations,
  unsupported cases, and the advisory nature of the review.

## Capabilities

### New Capabilities

- `github-ai-pr-review`: Securely review a newly opened pull-request diff with a
  configurable OpenCode Go model and publish an advisory comment.

### Modified Capabilities

None.

## Impact

- Adds a GitHub Actions workflow and a small review adapter or script under the
  repository's GitHub automation boundary.
- Uses GitHub pull-request APIs and the OpenCode Go API; it does not add a
  runtime dependency to the Python analyzer.
- Requires an `OPENCODE_GO_API_KEY` GitHub Actions secret and repository or
  organization permission to write pull-request comments.
- Introduces external processing of repository diff content. Provider retention,
  model-training, and repository confidentiality settings must be reviewed before
  enabling the workflow for private or untrusted pull requests.
- Does not change the CLI, frame filename contract, analyzer selection,
  progress files, result files, video processing, customer data flow, or gallery
  approval behavior.
