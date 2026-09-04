## 1. Workflow Boundary And Configuration

- [x] 1.1 Create a base-controlled, diff-only GitHub Actions workflow triggered by `pull_request_target` with the `opened` activity type and a same-repository head check that skips fork pull requests.
- [x] 1.2 Pin the workflow's third-party Actions to reviewed commit SHAs, use a standard GitHub-hosted Linux runner, set a bounded timeout and concurrency group, and disable checkout credential persistence.
- [x] 1.3 Configure least-privilege GitHub token permissions for reading repository content and writing pull-request comments without checking out or executing the pull-request head.
- [x] 1.4 Add documented `OPENCODE_GO_MODEL`, endpoint, and protocol configuration with `kimi-k2.7-code` as the default and validation for incompatible or missing settings.
- [x] 1.5 Document creation of the `OPENCODE_GO_API_KEY` repository or organization secret without adding any credential value to tracked files, workflow arguments, or generated artifacts.

## 2. Review Adapter

- [x] 2.1 Add a dependency-free Python automation adapter that reads GitHub event context, retrieves the pull-request diff through the GitHub API, and calls the configured OpenCode Go endpoint.
- [x] 2.2 Implement bounded patch collection that omits binary, media, generated, and excluded paths and reports truncation or skipped content to the renderer.
- [x] 2.3 Implement best-effort redaction for common API-key formats, authorization values, and private-key blocks before provider serialization.
- [x] 2.4 Construct a prompt that includes approved repository guidance, treats the diff as untrusted data, requests no-tool structured analysis, and includes a unique `x-opencode-session` value and identifying user agent.
- [x] 2.5 Implement chat-completions and Responses-style request handling behind the configured protocol boundary, including bounded timeouts and sanitized provider diagnostics.
- [x] 2.6 Validate the model response against the documented summary and finding schema, including severity, paths, line numbers, field types, output lengths, and finding-count limits.
- [x] 2.7 Render one concise advisory Markdown comment containing the model, reviewed commit, findings, and input limitations without raw prompts, patches, credentials, or unsanitized errors.
- [x] 2.8 Find and update the existing stable-marker comment before creating a new comment so retries are idempotent.

## 3. Tests And Verification

- [x] 3.1 Add offline unit tests for configuration selection, model/protocol validation, diff limits, excluded files, and common-secret redaction.
- [x] 3.2 Add offline tests for provider request construction, response parsing, malformed responses, timeout handling, and sanitized diagnostics using mocked HTTP transports.
- [x] 3.3 Add offline tests for deterministic comment rendering, advisory labeling, truncation notices, and stable-marker comment create/update behavior.
- [x] 3.4 Add workflow validation with a YAML/action linter where available and verify that the workflow cannot checkout or run pull-request-controlled files.
- [x] 3.5 Run `python3 -m unittest discover -s tests -v`, `python3 -m py_compile identify_clearest_frames.py`, and the automation adapter checks without model downloads, API credentials, or network access.
- [x] 3.6 Run `openspec validate` and `openspec validate --strict`, then perform a controlled same-repository pull request smoke test with the OpenCode Go secret configured.

## 4. Documentation And Rollout

- [x] 4.1 Update `README.md` or contributor documentation with workflow behavior, model switching, OpenCode Go usage limits, GitHub Actions billing, and the advisory-only boundary.
- [x] 4.2 Document provider privacy review requirements and explicitly exclude OpenCode Go models whose current terms permit training use from the recommended configuration.
- [x] 4.3 Test a valid review, an empty-findings review, an unavailable-secret failure, a provider timeout, an oversized diff, and a skipped fork pull request without exposing credentials.
- [x] 4.4 Enable the workflow in non-blocking mode, inspect permissions/logs/comments/provider usage, and record rollback steps including disabling the workflow and revoking the secret.
