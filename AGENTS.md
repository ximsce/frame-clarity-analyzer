# Agent Instructions

## Business Context

Before planning, reviewing, designing, or implementing behavior that affects
Wedding Glamour customers, read `BUSINESS_CONTEXT.md` and include its guidance
in the working context.

Before planning or changing technical boundaries, persistence, analyzer
integration, local engineer utilities, security, reliability, or test strategy,
read `PRODUCT_VISION.md` and `ARCHITECTURE.md` as well.

Treat `BUSINESS_CONTEXT.md` as authoritative business context. If business
context conflicts with feature requirements or implementation details, surface
the conflict and ask for clarification rather than silently choosing an
interpretation.

Do not invent missing business or technical policies. Raise unresolved
questions with the appropriate business or technical leaders.

## Evidence-Based Technical Decisions

Do not introduce arbitrary numeric limits for payloads, context, output tokens,
timeouts, retries, concurrency, file sizes, frame counts, or resource usage.
Before choosing a limit, identify its basis: an official provider or tool
document, a product or architecture requirement, a measured system constraint,
or an explicit owner decision. Record that basis in the relevant architecture,
OpenSpec, or user-facing documentation.

Keep these distinct and label them separately:

- vendor or model maximums;
- application safety budgets and conservative defaults; and
- workflow or job execution deadlines.

If a vendor maximum is undocumented, do not present an estimate as fact. Use a
clearly documented provisional budget, make it configurable where appropriate,
and record how it should be revisited.

## Third-Party Integration Diagnostics

Treat every third-party boundary as an operational interface. This includes LLM
and OpenAI-compatible calls, GitHub or other service APIs, FFmpeg/ffprobe, and
local model or analyzer runtimes such as CLIP.

Every integration must distinguish and safely diagnose:

- transport failures, HTTP status, timeouts, and remaining budget;
- provider or tool response-envelope failures;
- malformed or semantically invalid model/API output; and
- local process failures, exit codes, and bounded stderr where applicable.

Diagnostics must include useful sanitized metadata such as provider/tool
identity, protocol, status, request or correlation ID, content type, completion
reason, output shape, or executable exit code. Never log credentials, raw
prompts, raw diff content, raw model output, sensitive media, or unredacted
filesystem paths. Add offline tests for each expected failure class before
relying on live services.
