# github-ai-pr-review Specification

## Purpose

Provide a bounded, advisory AI review of newly opened pull requests using the
repository's OpenCode Go subscription without changing application behavior or
exposing the provider credential in repository-managed content.

## Requirements

### Requirement: Review newly opened pull requests

The workflow SHALL run on a GitHub-hosted standard runner for an eligible
non-draft pull request opened from a branch in the same repository and SHALL
obtain the pull request's proposed changes through GitHub's pull request API.
Fork-originated pull requests SHALL be skipped by the credentialed review job.

#### Scenario: Pull request is opened

- **WHEN** a non-draft pull request is opened
- **THEN** the workflow starts one AI review job and uses the pull request's
  current diff as the review input

#### Scenario: Workflow is not triggered by unrelated activity

- **WHEN** an issue, push, or unrelated repository event occurs
- **THEN** the AI review workflow does not run for that event

#### Scenario: Fork pull request is opened

- **WHEN** a non-draft pull request is opened from a fork repository
- **THEN** the credentialed AI review job does not run and the OpenCode Go secret
  is not made available to that pull request

### Requirement: Select the OpenCode Go model through configuration

The workflow SHALL select the OpenCode Go API endpoint and model through
repository or organization configuration, SHALL provide a documented default
model, and SHALL allow the model identifier to be changed without editing the
review logic.

#### Scenario: Default model is used

- **WHEN** the workflow runs without an overriding model configuration
- **THEN** it sends the review request to the documented default OpenCode Go
  model

#### Scenario: Model is overridden

- **WHEN** an authorized maintainer changes the configured model identifier
- **THEN** the next eligible workflow run uses that model without requiring a
  source-code change

#### Scenario: Model configuration is invalid

- **WHEN** the configured model or endpoint is missing or invalid
- **THEN** the job fails with a sanitized configuration diagnostic and does not
  publish a fabricated review

### Requirement: Protect the OpenCode Go credential

The workflow SHALL read the OpenCode Go API key only from a GitHub Actions secret
named `OPENCODE_GO_API_KEY` or an explicitly documented secure equivalent. The
credential MUST NOT be committed to the repository, written to artifacts,
included in workflow summaries or pull-request comments, or printed in logs.

#### Scenario: Credential is available to a trusted run

- **WHEN** an eligible run has access to the configured secret
- **THEN** the provider request authenticates using the secret in memory and no
  plaintext credential is persisted

#### Scenario: Credential is unavailable

- **WHEN** the workflow cannot access the provider secret
- **THEN** the job fails clearly without attempting an unauthenticated or
  alternative credential lookup

#### Scenario: Credential text is returned by an external failure

- **WHEN** the provider or workflow reports an error containing sensitive
  material
- **THEN** the diagnostic is sanitized before it reaches logs, artifacts, or the
  pull request

### Requirement: Review bounded, text-only change content

The workflow SHALL send only a bounded representation of the pull request diff
and approved repository guidance to OpenCode Go. It SHALL exclude binary files,
raw media, generated artifacts, and files outside the configured review scope,
and SHALL not execute pull-request-controlled code as part of the credentialed
review job.

#### Scenario: Small source change is reviewed

- **WHEN** the pull request contains source changes within the configured size
  and path limits
- **THEN** the model receives the relevant text diff and review guidance

#### Scenario: Diff exceeds the configured limit

- **WHEN** the pull request diff exceeds the configured input limit
- **THEN** the workflow truncates or skips the excess according to documented
  behavior and identifies that limitation in the resulting comment

#### Scenario: Binary or generated content is present

- **WHEN** the pull request contains binary, media, or excluded generated files
- **THEN** those contents are not sent to OpenCode Go and the review remains
  limited to eligible text changes

#### Scenario: Pull request contains executable workflow changes

- **WHEN** the pull request modifies workflow or review automation files
- **THEN** the credentialed job does not checkout or execute the pull request's
  modified code or workflow scripts

### Requirement: Publish validated advisory findings

The workflow SHALL require a structurally valid model response, SHALL post a
concise comment to the pull request containing the selected model and findings,
and SHALL identify the result as AI-generated and advisory. It MUST NOT represent
an invalid or unavailable response as a successful review.

#### Scenario: Model returns valid findings

- **WHEN** OpenCode Go returns a valid response containing zero or more supported
  findings
- **THEN** the workflow posts one advisory review comment with the findings and
  completes successfully

#### Scenario: Model returns malformed findings

- **WHEN** the response is malformed, empty, or outside the review response
  contract
- **THEN** the workflow rejects it, reports a sanitized failure, and does not
  publish the malformed content as a review

#### Scenario: Provider request fails

- **WHEN** the OpenCode Go request fails or times out
- **THEN** the workflow exits nonzero with a sanitized diagnostic and does not
  claim that the pull request passed AI review

### Requirement: Keep human review and merge authority

The AI workflow SHALL publish advisory feedback only. It SHALL NOT approve,
reject, merge, modify, or publish application changes, and its result SHALL NOT
replace required human review or deterministic project checks.

#### Scenario: Findings are present

- **WHEN** the model identifies possible defects or risks
- **THEN** the workflow presents them for maintainer evaluation without applying
  a merge decision

#### Scenario: No findings are present

- **WHEN** the model reports no actionable findings
- **THEN** the workflow communicates that result as an advisory signal and does
  not imply that the code is objectively correct or secure

### Requirement: Use least-privilege GitHub permissions

The workflow SHALL request only the GitHub token permissions required to read the
repository and write the pull-request comment, and SHALL use a bounded execution
time and concurrency policy appropriate for repeated pull-request activity.

#### Scenario: Workflow permissions are evaluated

- **WHEN** the workflow starts
- **THEN** the job has read access to the repository and only the documented
  pull-request write capability needed for its comment

#### Scenario: Workflow exceeds its execution budget

- **WHEN** the provider or GitHub API does not complete within the configured
  timeout
- **THEN** the job terminates and reports a sanitized failure without waiting
  indefinitely or publishing an unverified result
