# Frame Clarity Analyzer Product Briefing

## Purpose

Frame Clarity Analyzer is the media-processing component that turns wedding
video into a small, useful set of high-quality still-image candidates. Its
purpose is to reduce the effort required to find and preserve joyful moments
without asking people to search through every frame of a video themselves.

This document describes the product direction for this repository. It supports
human understanding and agentic development by distinguishing the current
implementation from the intended product, recording durable product principles,
and identifying decisions that remain open.

`BUSINESS_CONTEXT.md` is the authoritative source for Wedding Glamour business
facts and policies. This document applies that context to this product and must
not silently override it. When the two conflict, the conflict must be raised
for clarification.

## Product Vision

Given a private wedding video, the product should identify and prepare the most
useful still-image candidates for human review. The result should help couples,
planners, and authorized contributors preserve moments of joy for possible
sharing in Wedding Glamour's memory experience.

The product is review-first. It does not publish images directly to a shared
gallery. Every run produces a review queue, and gallery inclusion remains
subject to the couple's ownership and approval or explicitly granted
permissions.

The intended workflow is:

```text
Private wedding video
        |
        v
Video ingestion and frame extraction
        |
        v
Multi-dimensional quality assessment
        |
        v
Duplicate avoidance and candidate selection
        |
        v
Ranked stills with source provenance
        |
        v
Human review queue
        |
        v
Optional approved memory sharing
```

The CLI is the initial delivery mechanism. The eventual hosted architecture,
worker model, and required cloud services are intentionally undecided.

## Business Role

Wedding Glamour combines event planning, guest management, and memory sharing
through a connected web portal. This product belongs to the memory-sharing and
preservation part of that ecosystem.

After a wedding, attendees and vendors may have videos containing particular
moments of joy. Finding usable stills in those videos is burdensome. Frame
Clarity Analyzer is intended to make those moments easier to discover and review
while fitting into the broader private-gallery workflow.

The product should support the following business outcomes and principles:

- Create joy and togetherness by helping people find meaningful moments.
- Reduce stress and manual effort through dependable batch processing.
- Prefer simplicity and privacy over unnecessary engagement or automation.
- Deliver a quiet-luxury experience through calm, predictable, professional
  behavior rather than through visual styling alone.
- Earn trust through reliability, accessibility, transparent outcomes, and
  respect for customer control.

The specific usage level or behavior that defines success for the video feature
has not yet been determined. This briefing does not invent a usage target,
quality SLA, processing-time target, storage limit, or pricing model.

## Quality Definition

For this product, "high quality" means a combined assessment of:

- Sharpness and focus.
- Visibility of the relevant subject or subjects.
- Composition and visual appeal.
- Exposure and overall image readability.
- Facial expressions and the presence of a meaningful human moment when faces
  are relevant.
- Avoidance of duplicate or near-identical candidates.

The output is a ranking and review aid, not an objective declaration of
photographic truth. A score must not hide uncertainty or a processing failure.
The review queue allows a human to make the final decision.

The initial quality definition is product-owned and should be implemented
through explicit, testable analysis behavior. Later product work may:

- Refine the dimensions or their relative importance.
- Allow a user to define or adjust quality preferences.
- Let a user interact with an underlying LLM judge to express those preferences.

Those future capabilities must preserve privacy, explainability, and the
review-first boundary. They are not current requirements for the CLI.

## Review Queue Contract

The durable product output is a review queue of candidate stills, not an
automatically published gallery.

Each candidate should eventually retain enough information for a reviewer and
downstream systems to understand it, including:

- The still image or a retrievable reference to it.
- The source video identity and timestamp or frame position.
- The quality assessment and its component signals where available.
- The reason it was selected or any uncertainty relevant to review.
- Duplicate-group or related-candidate information when deduplication is used.
- Processing status and failure details when a candidate could not be assessed.

The current JSON output contains frame identity, numeric frame position, status,
score, reasoning, error detail, and attempt count. Future output changes should
extend this contract deliberately and document compatibility implications.

Review outcomes, gallery permissions, download rules, contributor controls,
moderation, and reporting remain governed by Wedding Glamour product decisions.
This repository must not invent those policies.

## Privacy, Ownership, And Retention

The product handles wedding memories and therefore follows these business
constraints:

- Wedding data is private by default.
- Couples own the wedding event data and shared memories, including control over
  access, edits, sharing, deletion, and export or download as those controls are
  defined by the broader product.
- Gallery content requires couple approval unless the couple has explicitly
  permitted other contributors to add content directly.
- Company administrators should not have access to wedding data.
- Event data and memories should be retained for up to 30 days after the couple
  ends payment, then hard deleted.

The current CLI has no hosted identity, permission, retention, or deletion
layer. Its future integration must preserve the constraints above rather than
assuming that local filesystem access is an acceptable substitute for product
authorization.

### Model Processing

Wedding imagery must be processed through local models by default or through an
external model that has been explicitly enabled and meets the required privacy
guarantees and restrictions against using the imagery or derived data for
training.

External processing is therefore an explicit trust boundary. A future adapter
must make that choice visible in configuration and user-facing operation, avoid
sending imagery by accident, and avoid placing credentials or sensitive media
details in logs, progress files, or error messages.

The current local CLIP analyzer is the preferred privacy-preserving path. The
current OpenAI analyzer is an optional external path and must only be used when
its provider and configuration satisfy the applicable privacy requirements.

## Current Product Boundary

The current implementation is the reliable analysis core of the larger vision.
It currently:

- Accepts a directory of numbered PNG images produced by another process.
- Validates the input set and orders frames numerically.
- Analyzes frames with a local CLIP model or an explicitly selected OpenAI
  vision model.
- Produces bounded ranking scores and optional reasoning.
- Represents success, failure, and skip outcomes explicitly.
- Checkpoints progress atomically and resumes matching work safely.
- Writes deterministic JSON results.
- Copies successful top-ranked frames for review or downstream use.
- Provides a CLI that can run locally without a database or hosted service.

The current implementation does not yet:

- Accept a video file as the input boundary.
- Decode a video or choose a frame-sampling strategy.
- Assess all quality dimensions defined by the target vision.
- Deduplicate near-identical frames.
- Preserve video timestamps or broader source provenance in its result contract.
- Provide a durable review-queue UI or workflow.
- Enforce user identity, permissions, retention, or deletion policies.
- Provide a library package, HTTP API, database, or cloud worker architecture.

These are capability gaps, not reasons to weaken the current reliability
contract.

## Expansion Path

Future work should expand the product in coherent stages:

1. **Video input boundary:** accept a video and establish a safe, resumable
   extraction workflow while retaining a usable frame-manifest abstraction.
2. **Frame analysis:** implement the defined quality dimensions with explicit
   scoring and failure semantics.
3. **Candidate selection:** select useful moments and avoid redundant
   near-identical frames without hiding excluded or failed inputs.
4. **Provenance and packaging:** retain source-video identity, timestamps,
   processing context, component signals, and artifacts needed for review.
5. **Review integration:** connect the CLI's output to a review queue without
   bypassing approval or privacy boundaries.
6. **Operational evolution:** evaluate hosted workers and cloud services only
   after the product, privacy, reliability, and cost requirements are defined.

The stages are directional. They do not establish commitments about cloud
architecture, supported video formats, processing time, availability, storage
cost, or other unresolved business and technical policies.

## Engineering Principles

Changes in this repository should follow these principles:

- **Review first:** produce candidates for human judgment; do not silently
  publish or delete content based only on a model score.
- **Privacy by construction:** keep local processing as the default and make
  external processing explicit, constrained, and observable.
- **Reliable batches:** preserve resumability, deterministic ordering, atomic
  checkpoints, and automation-safe exit statuses.
- **Honest results:** never convert an invalid response, unreadable input, or
  unresolved analysis error into a normal quality score.
- **Explainable selection:** retain enough evidence for people and agents to
  understand why a candidate was selected or rejected.
- **Stable boundaries:** keep video extraction, analysis, selection, storage,
  review integration, and model adapters separable so each can evolve without
  silently changing the others.
- **Offline-testable core:** default tests must not require model downloads,
  credentials, network access, or external services.
- **Small, explicit CLI:** preserve the CLI as the current primary interface and
  avoid speculative service or packaging work until the target architecture is
  decided.

## Guidance For Human And Agent Contributors

Before changing behavior that affects Wedding Glamour customers:

1. Read `BUSINESS_CONTEXT.md`.
2. Read this briefing for product intent and boundaries.
3. Read the relevant README and OpenSpec capability requirements.
4. Identify whether the change affects privacy, ownership, permissions,
   approval, retention, deletion, or external model processing.
5. Raise unresolved policy questions instead of inventing an answer.

Use the following source hierarchy:

- `BUSINESS_CONTEXT.md` defines authoritative business facts and policies.
- `PRODUCT_VISION.md` defines this repository's product direction and durable
  boundaries.
- `openspec/specs/` defines implemented or deliberately specified behavior.
- Active OpenSpec change artifacts define proposed scope and temporary design
  decisions.
- The code and README describe the currently shipped implementation.

When these sources disagree, do not silently reconcile them. Surface the
conflict, preserve privacy and customer control, and ask the appropriate
business or technical owner for clarification.

## Deferred Decisions

The following are intentionally outside this briefing or remain unresolved:

- Eventual cloud architecture and required services.
- Supported video formats and technical input limits.
- Processing-time, availability, and quality expectations.
- Storage limits and cost model.
- Detailed review-queue interaction design.
- Download, sharing, print-ordering, moderation, reporting, and contributor
  control policies.
- The exact success metric for video-feature usage.
- The final contract and evaluation method for user-defined quality preferences.

Future proposals may resolve these decisions, but must update the relevant
OpenSpec artifacts and preserve alignment with `BUSINESS_CONTEXT.md`.
