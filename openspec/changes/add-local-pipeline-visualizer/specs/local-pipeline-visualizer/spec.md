## Purpose

This capability provides a small local browser interface for exercising the
video-to-frame pipeline and inspecting ranked candidates without creating a
hosted review product or changing the existing CLI workflow.

## ADDED Requirements

### Requirement: The visualizer runs as a local-only engineer utility

The system SHALL provide a documented local command that starts the visualizer
and serves its interface on the loopback network by default. The visualizer
SHALL be identified as an engineer tool and SHALL not require or imply a hosted
identity, customer account, gallery, or shared review session.

#### Scenario: The utility starts locally

- **WHEN** a developer starts the documented visualizer command
- **THEN** the interface is available through a browser on the local machine and
  the server is not bound to a non-loopback interface by default

#### Scenario: The utility does not create customer review behavior

- **WHEN** a developer completes a visualizer run
- **THEN** the interface provides inspection results only and has no controls for
  approval, rejection, publishing, sharing, or gallery inclusion

### Requirement: A developer can submit one local video run

The visualizer SHALL allow a developer to choose one local video file through
the browser and submit it for processing. The submitted bytes SHALL be stored in
an isolated run workspace, and the visualizer SHALL reject an invalid upload or
an upload that exceeds its configured local resource limit before analysis
begins.

#### Scenario: A selected video is accepted

- **WHEN** the developer selects a readable supported video within the local
  resource limit and starts a run
- **THEN** the visualizer creates an isolated run and begins the existing video
  validation and extraction workflow

#### Scenario: Invalid video input is rejected

- **WHEN** the selected file is missing, unreadable, unsupported, lacks a usable
  video stream, or exceeds the configured duration or upload limit
- **THEN** the visualizer displays a clear error, does not begin frame analysis,
  and leaves no run available as a successful result

#### Scenario: A second run is not started concurrently

- **WHEN** a developer submits another video while one visualizer run is active
- **THEN** the interface prevents the second run from starting and preserves the
  state of the active run

### Requirement: Web runs use bounded local CLIP analysis

The visualizer SHALL use the local CLIP analyzer and SHALL not expose OpenAI or
another external analyzer as a web option. Web runs SHALL default to a sampling
density of 5 frames per second and SHALL offer a bounded option at 30 frames per
second, with no selectable sampling value greater than 30 frames per second.
The CLI's analyzer choices and sampling defaults SHALL remain unchanged.

#### Scenario: The default web sampling is fast

- **WHEN** the developer opens a new visualizer run without changing settings
- **THEN** the sampling setting is 5 frames per second and the run uses local
  CLIP analysis

#### Scenario: The maximum web sampling is available

- **WHEN** the developer selects the highest offered sampling setting
- **THEN** the visualizer accepts 30 frames per second and passes that setting to
  the existing video workflow

#### Scenario: External analysis is unavailable in the web UI

- **WHEN** the developer configures or submits a run through the visualizer
- **THEN** the interface provides no OpenAI analyzer selection and does not send
  the video or extracted frames to an external analyzer

### Requirement: Processing status is visible and non-blocking

The visualizer SHALL process an accepted run without requiring the browser
request to remain open until analysis completes. It SHALL expose the current run
phase and available progress, including validation, extraction, analysis,
completion, and failure states. A failed run SHALL retain and display any valid
diagnostic and result artifacts that were produced before the failure.

#### Scenario: Analysis progress is displayed

- **WHEN** an accepted run is analyzing frames
- **THEN** the interface displays that the run is analyzing and reports the
  available processed, successful, and failed counts

#### Scenario: Extraction is still in progress

- **WHEN** video extraction has started but a complete extraction manifest is not
  yet available
- **THEN** the interface displays an extraction-in-progress state and does not
  display the run as complete

#### Scenario: Processing failure is visible

- **WHEN** validation, extraction, model initialization, persistence, or frame
  analysis fails
- **THEN** the interface displays a failure state and a sanitized diagnostic,
  without converting the failure into a successful result

### Requirement: Ranked frame candidates can be inspected

After a complete analysis result is available, the visualizer SHALL display
successful candidates in the same deterministic ranking order as the existing
results workflow. Each displayed candidate SHALL include its rank, bounded
score, image, source timestamp when available, and analyzer reasoning when
available. Failed or skipped frames SHALL not be displayed as successful
candidates.

#### Scenario: Successful candidates are shown in rank order

- **WHEN** a run completes with successful frame outcomes
- **THEN** the interface displays the ranked successful frame images in
  descending score order with numeric frame-order tie breaking

#### Scenario: Candidate metadata is visible

- **WHEN** a displayed candidate originated from the submitted video
- **THEN** the interface displays its source timestamp and the available CLIP
  score and reasoning alongside the image

#### Scenario: Failed frames remain distinguishable

- **WHEN** one or more frames fail during analysis
- **THEN** the interface reports those failures separately with their diagnostic
  details and does not present them as selected candidates

### Requirement: Run artifacts are private to the local run and temporary

The visualizer SHALL serve images and metadata only from the active or completed
run's isolated workspace and SHALL prevent a request from addressing arbitrary
filesystem paths. Run workspaces SHALL be temporary session artifacts and SHALL
be cleaned up when the visualizer process exits or when the developer explicitly
clears the run.

#### Scenario: A frame is served only for its run

- **WHEN** the browser requests a displayed candidate image
- **THEN** the visualizer serves the corresponding image from that run and does
  not resolve user-controlled path traversal or unrelated filesystem paths

#### Scenario: Session artifacts are cleaned up

- **WHEN** the visualizer process exits or the developer clears the current run
- **THEN** uploaded video, extracted frames, progress, results, and copied frame
  artifacts for that run are removed or otherwise made unavailable

### Requirement: The visualizer preserves existing CLI behavior

Adding the visualizer SHALL not change the existing numbered-PNG input mode,
CLI invocation, CLI 30 FPS default, analyzer selections, progress and resume
semantics, result JSON contract, or rank-prefixed copied-frame behavior.

#### Scenario: Existing CLI behavior remains available

- **WHEN** a developer invokes the documented CLI independently of the
  visualizer
- **THEN** the CLI continues to process its supported inputs with its existing
  defaults and artifacts

#### Scenario: Web results match the existing workflow

- **WHEN** the visualizer completes a run using a given video, sampling setting,
  and local CLIP context
- **THEN** its displayed candidates and statuses correspond to the same
  extraction, manifest, analysis, and deterministic ranking contracts used by
  the CLI workflow

### Requirement: The visualizer is testable without external services

The project SHALL test the visualizer's upload, run-state, error, result, and
run-scoped image-serving behavior using local fixtures, fakes, or mocks. The
default test suite SHALL not require a downloaded model, network access, API
credentials, API credits, or a live external service.

#### Scenario: The default visualizer tests run offline

- **WHEN** the default test suite runs without model files, credentials, or
  network access
- **THEN** visualizer behavior is exercised through local test doubles and the
  suite completes without external analyzer calls
