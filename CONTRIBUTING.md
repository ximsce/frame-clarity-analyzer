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

## Development Tool Installation

The following instructions are for macOS. Install the tools once per machine,
then verify them from the repository root.

### Visual Studio Code

1. Install [Visual Studio Code for macOS](https://code.visualstudio.com/docs/setup/mac).
2. Open VS Code, press `Cmd+Shift+P`, and run **Shell Command: Install 'code'
   command in PATH**.
3. Verify the command from a terminal:

   ```bash
   code --version
   ```

### OpenCode

OpenCode runs in a terminal and can also integrate with VS Code. Install it with
Homebrew:

```bash
brew install anomalyco/tap/opencode
opencode --version
```

Run `opencode` from this repository to start a session. OpenCode also needs an
API key for the model provider you choose; use `/connect` in the OpenCode
interface or follow the [OpenCode setup documentation](https://opencode.ai/docs/).

### OpenSpec

OpenSpec requires Node.js 20.19.0 or newer. If Node.js is not installed, install
it with Homebrew and verify the version:

```bash
brew install node
node --version
```

Install the OpenSpec CLI globally and verify it is on your `PATH`:

```bash
npm install -g @fission-ai/openspec@latest
openspec --version
```

This repository is already initialized for OpenSpec. Do not run `openspec init`
in this checkout unless you intentionally need to recreate its project setup.
Verify the local installation with:

```bash
openspec doctor
openspec validate
```

### Other Platforms

Use the vendor documentation for platform-specific installation details:

- [Homebrew installation](https://brew.sh/) for macOS and Linux package management;
- [Visual Studio Code downloads and setup](https://code.visualstudio.com/download);
- [OpenCode installation and Windows/WSL guidance](https://opencode.ai/docs/);
- [OpenSpec installation](https://openspec.dev/docs/installation); and
- [Node.js downloads](https://nodejs.org/en/download/) for Windows, Linux, and macOS.

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

## OpenCode Go Pull-Request Review

The repository includes an advisory GitHub Actions workflow that reviews
non-draft pull requests opened from branches in this repository. It runs on a
standard GitHub-hosted Linux runner, retrieves the diff through the GitHub API,
and posts one AI-generated comment. It does not approve, reject, merge, modify,
or replace human review and deterministic checks. Fork-originated pull requests
are skipped.

To enable the workflow, configure the following outside the repository:

- Add the OpenCode Go API key as a repository or organization Actions secret
  named `OPENCODE_GO_API_KEY`.
- Optionally add an Actions variable named `OPENCODE_GO_MODEL`. The default is
  `kimi-k2.7-code`.
- Optionally add matching `OPENCODE_GO_ENDPOINT` and `OPENCODE_GO_PROTOCOL`
  variables when selecting a model from another OpenCode Go API family. The
  supported protocols are `chat-completions` and `responses`.

Never put the API key in a workflow argument, source file, repository variable,
commit, issue, pull-request comment, or generated artifact. The workflow uses a
base-controlled `pull_request_target` job and must not be changed to checkout
or execute the pull-request head.

OpenCode Go usage is governed by the provider's current subscription limits and
model catalog. Repeated reviews consume the subscription allowance. Review the
current [OpenCode Go documentation](https://opencode.ai/docs/go/) before
selecting a model; do not use a model whose current terms permit training use
for private repository code. The review sends bounded, text-only diff content
and approved repository guidance to OpenCode Go, with best-effort redaction of
common credentials. Redaction cannot guarantee detection of arbitrary secrets.

The workflow uses no project dependency installation and normally produces no
Actions artifacts. Standard runners are free for public repositories. Private
repositories use their GitHub Actions minutes and storage allowance, with
additional usage billed according to the repository owner's GitHub plan. See
[GitHub Actions billing](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions).

If the workflow must be disabled, turn off the workflow in repository Actions
settings. If a provider credential may have been exposed, revoke it at
OpenCode and replace the GitHub Actions secret.

## Data and Generated Files

Do not commit raw video frames, copied clear frames, API keys, progress files, or
analysis result files. The repository ignores the current generated JSON and
output directory, but verify `git status` before creating a commit.
