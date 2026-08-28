## Purpose

This capability lets the local CLI accept short video files, extract a
deterministic set of still frames for analysis, and retain enough source timing
and extraction context for human review.

## ADDED Requirements

### Requirement: Video input is validated before extraction

The system SHALL accept a local video file through the video input mode and
SHALL validate that the path exists, is a regular readable file, contains a
usable video stream, and has a duration no greater than 180 seconds. The system
SHALL validate the required local media tools before extraction begins. A missing,
unreadable, unsupported, duration-unknown, or longer-than-180-second input SHALL
produce a clear diagnostic, SHALL not begin frame analysis, and SHALL return a
nonzero exit status.

#### Scenario: A valid short video passes preflight

- **WHEN** the user supplies a readable video file with a usable video stream and a duration of 180 seconds or less
- **THEN** the CLI accepts the input and proceeds to the configured extraction stage

#### Scenario: A video longer than three minutes is rejected

- **WHEN** the supplied video has a duration greater than 180 seconds
- **THEN** the CLI reports the duration-limit failure before extraction or analysis and returns a nonzero exit status

#### Scenario: Invalid video input is rejected clearly

- **WHEN** the supplied path is missing, unreadable, not a regular file, has no usable video stream, or has no determinable duration
- **THEN** the CLI identifies the input failure and returns a nonzero exit status without starting analysis

#### Scenario: Required media tools are unavailable

- **WHEN** the video mode cannot access a required local media tool
- **THEN** the CLI reports the missing prerequisite and returns a nonzero exit status without starting extraction

### Requirement: Video frames are sampled and materialized deterministically

The system SHALL sample video at a default density of 30 frames per second and
SHALL allow the resulting frames to be processed by the existing frame-analysis
workflow. Extracted frames SHALL be materialized as individually addressable PNG
files with deterministic numeric identities in an isolated workspace that cannot
be contaminated by unrelated PNG files. The same source video and extraction
configuration SHALL produce the same frame identities and ordering.

#### Scenario: Default sampling produces numbered PNG frames

- **WHEN** the user processes a valid video without overriding sampling density
- **THEN** the extraction produces individually addressable numbered PNG frames using a 30-frames-per-second sampling plan

#### Scenario: Extraction output is isolated

- **WHEN** video frames are extracted for analysis
- **THEN** only the frames belonging to that extraction are presented to frame discovery and unrelated files cannot change the discovered input set

#### Scenario: Repeating extraction is deterministic

- **WHEN** the same video and extraction configuration are processed more than once
- **THEN** the extracted frame identities, numeric order, and source-time associations are stable

### Requirement: Video extraction uses safe artifact-level restart

The system SHALL publish an extracted frame set only after extraction completes
successfully and the resulting artifacts and extraction metadata have been
validated. A completed extraction MAY be reused only when its source identity and
extraction configuration match the current request. An interrupted or failed
extraction SHALL not be treated as complete; its temporary artifacts SHALL be
discarded or isolated from future analysis, and a later resumed run SHALL restart
extraction from the beginning. A complete extraction SHALL remain independently
reusable by the analysis progress workflow.

#### Scenario: Completed matching extraction is reused

- **WHEN** a prior extraction is complete and its source identity and sampling configuration match the current request
- **THEN** the CLI reuses the complete extraction instead of treating it as a new frame set

#### Scenario: Interrupted extraction restarts safely

- **WHEN** extraction is interrupted before its artifacts are published as complete
- **THEN** the incomplete artifacts are not analyzed and the next run restarts extraction from the beginning

#### Scenario: Failed extraction cannot yield a successful analysis

- **WHEN** the extractor fails or produces an invalid incomplete frame set
- **THEN** the CLI reports the extraction failure, does not analyze the incomplete set, and returns a nonzero exit status

### Requirement: Video-derived frames retain extraction provenance

The system SHALL associate each video-derived frame result with provenance that
includes a stable source-video identity, source video filename or safe local
identifier, source video stream identity, the frame's source timestamp in
seconds, and the extraction sampling configuration. Provenance SHOULD include the
actual decoded timestamp when it differs from or is available in addition to the
requested sample timestamp. Provenance SHALL not include API keys or an
unnecessary absolute local path.

#### Scenario: Video result includes source provenance

- **WHEN** a sampled video frame receives an analysis outcome
- **THEN** its results JSON record contains the source identity, stream identity, source timestamp, and sampling configuration needed to locate and understand the frame

#### Scenario: Provenance remains stable across deterministic reruns

- **WHEN** the same source video, sampling configuration, and extraction context are processed again
- **THEN** the corresponding frame records retain the same source identities and timestamps

#### Scenario: Sensitive local details are not exposed unnecessarily

- **WHEN** provenance is written to extraction or results artifacts
- **THEN** it does not persist credentials or an unnecessary absolute local filesystem path

### Requirement: Extraction failures remain visible and automation-safe

The system SHALL distinguish extraction failures from successful frame analysis.
An extractor error, unreadable extracted frame, invalid extraction metadata, or
failure to publish required extraction artifacts SHALL produce a visible
diagnostic and a nonzero exit status. The system SHALL never convert an
extraction failure into a normal frame quality score.

#### Scenario: Media decoder failure is reported

- **WHEN** the local decoder cannot read or decode the supplied video
- **THEN** the CLI reports the decoder failure and exits nonzero without presenting the run as successful

#### Scenario: Required extraction artifact cannot be written

- **WHEN** the system cannot publish the extracted frame set or its metadata
- **THEN** the CLI reports the persistence failure and exits nonzero
