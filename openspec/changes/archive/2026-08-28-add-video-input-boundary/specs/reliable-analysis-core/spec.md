## MODIFIED Requirements

### Requirement: Results and copied outputs preserve the existing contract

The system SHALL continue to write the full JSON results beside the input
directory at `frame_analysis_results.json` by default and progress at
`frame_analysis_progress.json` by default. The results SHALL include all frame
outcomes, status, score where applicable, reasoning where available, error
details for failures, and the configured top-N value. When copying is enabled,
successful top frames SHALL be copied to the configured output directory,
defaulting to the parent directory's `clearest_frames`, using the existing
numeric rank prefix. For video-origin frames, each result SHALL additionally
retain the source-video identity, source stream identity, source timestamp, and
extraction configuration required by the video-input capability. Existing
numbered-PNG directory results SHALL remain valid without video provenance
fields.

#### Scenario: Default artifacts remain discoverable

- **WHEN** the command is run without custom progress, results, or output paths
- **THEN** it writes the progress and results files beside the frames directory and copies eligible top frames to the parent `clearest_frames` directory

#### Scenario: No-save suppresses copies only

- **WHEN** the user invokes the documented `--no-save` option
- **THEN** the JSON results are still generated and frame copies are not written

#### Scenario: Video results retain provenance

- **WHEN** a video-origin frame is included in the results JSON
- **THEN** its record contains source-video identity, source stream identity, source timestamp, and extraction configuration in addition to the existing outcome fields

#### Scenario: Existing frame-directory results remain compatible

- **WHEN** the user analyzes an existing numbered-PNG frame directory
- **THEN** the command preserves the existing result fields, ranking behavior, copied filenames, and artifact locations without requiring video provenance
