## Context

The current repository has no GitHub Actions workflow. The Python application is
a local CLI with a heavyweight model dependency set, while this capability only
needs to exchange a pull-request diff and a text response. The existing
reliability and security guidance requires external API failures to remain
explicit, credentials to stay out of logs and persisted artifacts, and default
tests to work without credentials or network access. See `proposal.md` for the
motivation and `specs/github-ai-pr-review/spec.md` for the behavior contract.

The OpenCode Go subscription exposes API-key-authenticated endpoints for coding
agents. Its model catalog includes both chat-completions and Responses-style
endpoints, so the adapter must retain the endpoint/protocol distinction while
keeping routine model selection simple.

## Goals / Non-Goals

**Goals:**

- Run one bounded advisory review for a newly opened pull request.
- Avoid exposing the provider credential to fork pull requests.
- Use a small automation adapter that does not install the application's
  PyTorch, Transformers, or CLIP dependencies.
- Make the normal model change a repository or organization variable change.
- Make provider failures, malformed model output, truncation, and unavailable
  credentials diagnosable without disclosing sensitive values.
- Keep the review idempotent so a retry does not create an unbounded series of
  duplicate comments.

**Non-Goals:**

- Reviewing on every commit push, scheduled review, issue command, or manual
  dispatch in the initial capability.
- Running project tests, linters, the frame analyzer, or arbitrary pull-request
  code in the credentialed job.
- Inline line-level review threads, automatic fixes, approvals, merge decisions,
  or required status gating.
- Processing wedding images, videos, generated analysis output, or any other
  binary repository content.
- Creating a hosted service, database, package, or reusable public Action.

## Decisions

### Use a diff-only `pull_request_target` workflow for same-repository branches

The workflow will listen for `pull_request_target` with the `opened` activity
type and will require the pull request head repository to match the base
repository. Fork-originated pull requests will be skipped before the provider
secret is passed to any process. The job will check out only the trusted base
branch, or use trusted workflow-resident code, and will obtain the proposed
changes through the authenticated GitHub pull-request API. It will never check
out the pull request head or execute files supplied by the contributor.

This deliberately trades fork coverage for a smaller credential exposure
surface. `pull_request_target` is used because the workflow executes from the
trusted base revision and can therefore keep the review script out of the
pull-request-controlled workspace. A normal `pull_request` event would be
safer by default, but same-repository workflow changes could otherwise affect
the credentialed run and fork events cannot use the secret.

The workflow and all third-party Actions will be pinned to reviewed commit SHAs.
The checkout will disable credential persistence. The GitHub token will be
limited to repository contents read access and pull-request write access.

### Use a dependency-free Python adapter

The implementation will add a small script under the GitHub automation boundary
using Python's standard library for HTTPS, JSON, environment access, response
validation, and comment publication. The workflow will use the runner's Python
runtime and will not install `requirements.txt`.

This is preferable to invoking `identify_clearest_frames.py`, whose dependencies
and purpose are unrelated, and avoids adding a Node package or a second
application integration surface. The adapter will expose pure functions for
diff limiting, redaction, response parsing, and comment rendering so they can be
tested with local fixtures and mocked HTTP calls.

### Configure model and protocol separately

The workflow will use an `OPENCODE_GO_MODEL` repository or organization variable,
with `kimi-k2.7-code` as the documented default. The OpenCode Go endpoint and
request format will also be configuration values with safe defaults for that
model family:

- chat-completions models use
  `https://opencode.ai/zen/go/v1/chat/completions`;
- Responses models use
  `https://opencode.ai/zen/go/v1/responses`.

The adapter will validate that the selected protocol produces the expected
response shape and will fail safely on invalid configuration. This keeps common
model switching to one variable while allowing a model from another OpenCode Go
protocol family to be selected deliberately by changing the corresponding
configuration. The model catalog and transient pricing or usage limits will be
documented as provider-managed rather than copied into application contracts.

Each request will include `Authorization: Bearer <secret>`, a narrow identifying
user agent, and a unique `x-opencode-session` value derived from the repository,
pull-request number, and commit SHA without including the API key.

### Send bounded, redacted text context

The adapter will retrieve the patch from GitHub, reject or omit binary and
generated files, apply a maximum byte and line budget, and include only approved
repository guidance such as `CONTRIBUTING.md` and the relevant architecture
guidance. Common credential formats and private-key blocks will be redacted
before the request is serialized. The redaction is a defense-in-depth measure,
not a guarantee that arbitrary secrets can be detected.

The prompt will clearly delimit the diff as untrusted data and instruct the model
to ignore instructions contained in source comments, strings, or documentation.
The request will not enable model tools, shell execution, repository writes, or
any action beyond producing structured findings.

### Require and validate a stable response shape

The model will be asked for a JSON object containing a short summary and a list
of findings. Each finding will contain a severity from a fixed set, a file path,
an optional line number, a concise title, an explanation, and an optional
suggestion. The adapter will validate types, severity values, output lengths,
and the maximum number of findings before rendering Markdown.

Invalid JSON, unsupported fields required for rendering, provider errors, and
timeouts will produce a nonzero job result. Raw provider responses and exception
text will not be copied into logs or comments.

### Publish one marked advisory comment

The adapter will post an issue comment using a stable hidden marker, for example
`<!-- opencode-go-ai-review -->`. Before creating a comment it will search for
the marker and update an existing bot comment when present. This makes retries
idempotent and prevents duplicate comments if a runner is restarted.

The comment will name the selected model, state that the result is AI-generated
and advisory, identify truncation or skipped-content limitations, and render
validated findings. It will not contain the provider key, raw prompts, raw
patches, or unsanitized provider errors. It will not use GitHub's approve or
request-changes review states.

### Treat credential availability and provider usage as deployment configuration

The secret will be named `OPENCODE_GO_API_KEY` and configured outside the
repository through GitHub Actions repository or organization secrets. The
workflow will pass it only to the adapter process and will not place it in
command-line arguments, files, artifacts, comments, or job summaries.

The documentation will explain that OpenCode Go has provider-managed time and
usage limits, that repeated workflow runs consume that allowance, and that any
optional balance fallback can create additional charges. A maintainer must
select a Go model whose current data-handling terms are acceptable; models whose
terms permit training use will not be the documented default.

### Test the adapter offline and the workflow statically

Unit tests will cover redaction, byte and line limits, model/protocol
configuration, response validation, sanitized diagnostics, deterministic
rendering, and marker-based comment updates using mocked HTTP transports.
Workflow tests will validate YAML and action configuration with a workflow linter
where available. The existing Python test suite and CLI checks will remain
independent of OpenCode Go credentials, model downloads, and network access.

## Risks / Trade-offs

- **`pull_request_target` can expose secrets if its boundary is violated** -> Do
  not checkout the PR head, execute contributor-controlled files, interpolate
  untrusted content into shell commands, or allow the model to use tools; pin
  Actions and review the workflow as security-sensitive code.
- **A diff can contain an unknown secret** -> Exclude binary/generated content,
  redact common credential patterns, cap the payload, document that redaction is
  best-effort, and maintain repository secret-scanning controls separately.
- **Prompt injection can influence the model's findings** -> Treat the patch as
  untrusted data, use a no-tools request, require strict output validation, and
  keep the result advisory.
- **Model output can be incorrect or noisy** -> Ask only for high-confidence,
  actionable findings, label every result as advisory, and preserve human review
  and deterministic checks as the merge authority.
- **OpenCode Go model protocols differ** -> Keep model, endpoint, and protocol
  configuration explicit, validate combinations, and document supported model
  families rather than silently guessing an endpoint.
- **Provider limits can make review availability variable** -> Use one request
  per opened pull request, enforce timeouts and input limits, avoid automatic
  retries that multiply usage, and report unavailable reviews as failures.
- **Workflow comments can become stale or duplicated** -> Use a stable marker,
  update the existing bot comment, and include the reviewed commit SHA.
- **GitHub Actions billing may apply to private repositories** -> Use a standard
  Linux runner, avoid dependency installation and artifacts, set a timeout, and
  document the runner-minute implications separately from OpenCode Go usage.

## Migration Plan

1. Add the workflow, adapter, offline tests, and configuration documentation in
   a same-repository pull request that can be reviewed without the workflow
   secret.
2. Configure `OPENCODE_GO_API_KEY` in GitHub repository or organization secrets
   and set the selected model/protocol variables in GitHub repository or
   organization variables.
3. Enable the workflow first as advisory-only and exercise it against a small
   internal pull request, verifying logs, permissions, provider usage, and the
   absence of credential leakage.
4. Keep the workflow non-blocking while maintainers evaluate review quality. No
   data migration is required.
5. Roll back by disabling or deleting the workflow and revoking the GitHub secret
   if exposure is suspected. Existing pull-request comments remain ordinary
   GitHub comments and do not affect application state.
