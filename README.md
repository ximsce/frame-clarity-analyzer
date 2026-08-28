# Frame Clarity Analyzer

Frame Clarity Analyzer ranks video frames by perceived clarity. It is a
command-line Python utility, not a video editor or a hosted service. Give it a
local video file or a directory of numbered PNG images and it produces a ranked
report plus an optional folder of the best frames. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the current-phase architecture, testing
boundaries, and security considerations.

The product direction is end-to-end video-to-high-quality-frame extraction, with
all outputs entering a human review queue. See [PRODUCT_VISION.md](PRODUCT_VISION.md)
for the product briefing, business role, privacy boundaries, and planned
expansion from the current frame-ranking core.

The project supports two analyzer backends:

- `clip`: a local Hugging Face CLIP model. This is the default and does not incur
  per-image API charges after the model has been downloaded.
- `openai`: an OpenAI vision model. This requires an API key, account credits,
  and network access.

Video extraction uses the locally installed `ffprobe` and `ffmpeg` command-line
tools. Video processing does not upload the source video by itself.

## Current Scope

The current implementation focuses on ranking individual images. It does not:

- deduplicate near-identical frames;
- guarantee objective photographic sharpness;
- provide a library package or HTTP API; or
- persist results in a database.

## Requirements

- Python 3.9 or newer
- Dependencies listed in `requirements.txt`
- `ffmpeg` and `ffprobe` on `PATH` for video input
- A local model download and enough memory for CLIP mode
- An `OPENAI_API_KEY` and OpenAI billing for OpenAI mode

On macOS, install the local media tools with Homebrew:

```bash
brew install ffmpeg
ffmpeg -version
ffprobe -version
```

Install the pinned project dependencies in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The current `torch==2.1.1` dependency requires NumPy 1.x compatibility. Install
the compatible range and verify the environment with the same interpreter used
to run the CLI:

```bash
python -m pip install --upgrade "numpy<2"
python -m pip check
```

`openai` is installed by the current requirements file even when using CLIP.
The script treats it as optional at runtime, but dependency installation is not
yet split into separate extras.

## Input Contract

The scanner currently considers only files matching `*.png`. File stems must
contain a numeric frame index after the configured prefix:

```text
rawFrames0001.png
rawFrames0002.png
rawFrames0003.png
```

The prefix is read from `FRAME_PREFIX` when the script starts and defaults to
`rawFrames`:

```bash
FRAME_PREFIX=myFrames python identify_clearest_frames.py \
  --frames-dir extracted_frames
```

The numeric index is used for ordering. Files with unexpected names are rejected
with a diagnostic naming the invalid file, and the command exits nonzero.

Note that the code's CLI directory default is `dancingFrames`, while the naming
prefix default is `rawFrames`. For predictable behavior, pass `--frames-dir`
explicitly and make the prefix match the actual filenames.

## Video Input Contract

Use `--video` to process one local video file. The CLI validates the file with
`ffprobe`, selects a usable video stream, and rejects videos longer than 180
seconds before extraction or model initialization. The default sampling density
is 30 frames per second and can be changed with `--sample-fps`.

Frames are extracted as numbered PNG files in an isolated workspace named from
the video, with a `video_extraction_manifest.json` file containing source
identity, stream context, sampling settings, and per-frame timestamps. A
completed matching workspace may be reused. An interrupted or failed extraction
is discarded and restarted from the beginning rather than being analyzed as a
partial set.

The first video workflow is local and CLI-driven. It does not connect to a phone,
provide hosted upload or identity behavior, publish to a gallery, deduplicate
frames, or provide a review UI.

## Quick Start

Run local CLIP analysis from the project root:

```bash
python identify_clearest_frames.py \
  --frames-dir rawFrames \
  --top-n 50 \
  --analyzer clip
```

Run OpenAI analysis sequentially with the default rate-limit safeguards:

```bash
OPENAI_API_KEY=sk-... python identify_clearest_frames.py \
  --frames-dir rawFrames \
  --analyzer openai \
  --model gpt-4o
```

Run local CLIP analysis directly from a short video:

```bash
python identify_clearest_frames.py \
  --video wedding-clip.mov \
  --analyzer clip
```

At the default 30 FPS, a three-minute video can produce up to 5,400 extracted
frames. This can require substantial disk space and analysis time.

Do not place API keys directly in source files or commit them. An environment
variable is preferred to `--api-key` because command-line arguments may be
visible in local process listings or shell history.

## Command-Line Options

| Option | Default | Description |
| --- | --- | --- |
| `--frames-dir` | `dancingFrames` | Directory containing numbered PNG frames |
| `--video` | off | Local video file to extract frames from |
| `--extraction-dir` | Video-derived | Directory for video extraction artifacts |
| `--sample-fps` | `30` | Video sampling density in frames per second |
| `--output-dir` | Parent/`clearest_frames` | Destination for copied top frames |
| `--progress-file` | Parent/`frame_analysis_progress.json` | Progress JSON path |
| `--results-file` | Parent/`frame_analysis_results.json` | Results JSON path |
| `--batch-size` | `10` | Number of frames between progress checkpoints |
| `--top-n` | `50` | Number of top frames to copy and display |
| `--analyzer` | `clip` | `clip` or `openai` |
| `--clip-model` | `openai/clip-vit-base-patch32` | Hugging Face model for CLIP mode |
| `--model` | `gpt-4o` | OpenAI model for OpenAI mode |
| `--max-workers` | `1` | OpenAI concurrency when free-tier mode is disabled |
| `--no-save` | off | Write the JSON report but do not copy frames |
| `--no-free-tier` | off | Allow configured OpenAI concurrency and shorter pacing |
| `--no-resume` | off | Ignore existing progress and process all frames |
| `--requests-per-minute` | `3` | OpenAI request limit |
| `--delay-between-requests` | `20.0` | Minimum OpenAI request delay in seconds |
| `--format` | `text` | Console output format: `text` or `json` |

Use `python identify_clearest_frames.py --help` for the complete CLI help.

## How Scoring Works

CLIP compares each image with six quality-related text prompts, including sharp,
blurry, high-quality, and poorly composed descriptions. Weighted positive and
negative prompt probabilities are combined into a score from 0 to 100. This is a
heuristic ranking signal, not a calibrated sharpness measurement.

OpenAI mode sends each PNG to the selected vision model and asks for a JSON
object containing a `score` from 0 to 100 and a short explanation. Responses are
strictly validated; malformed, missing, nonfinite, or out-of-range scores fail
the frame instead of receiving a fallback score. Retryable API failures are
retried with synchronized rate limiting.

## Generated Artifacts

For an input directory such as `project/rawFrames`, the default artifacts are:

- `project/frame_analysis_progress.json`: resumable state saved after each batch;
- `project/frame_analysis_results.json`: the complete ranked outcome list;
- `project/clearest_frames/001_rawFrames0001.png`: ranked copies of top frames.

For a video such as `project/wedding-clip.mov`, the default extraction workspace
is `project/wedding-clip_frames/` and contains the numbered extracted PNGs plus
`video_extraction_manifest.json`. Results and analysis progress are written
beside that workspace unless custom paths are supplied.

The full results list contains one record per discovered frame. Each record has a
`status` of `success`, `failed`, or `skipped`; successful records have a score,
while failed and skipped records have a null score and an error/reason field.
Successful records are ranked by descending score with numeric frame-number tie
breaking. Failed or skipped frames are never copied to the top-frame directory.

Progress is versioned, written atomically after each batch, and records the input
set identity, analyzer, model, scoring version, statuses, and attempt counts. On
resume, successful matching frames are reused and failed frames are retried.
Changed input files or analyzer/model settings produce a metadata-mismatch error;
use `--no-resume` to intentionally start a new context. Structurally valid legacy
progress files are migrated, while corrupt or ambiguous files are rejected.

Video result records additionally include a stable source-video identity, source
stream identity, source timestamp, requested sampling timestamp, and extraction
configuration. Credentials and unnecessary absolute local paths are not stored.

For automation, exit status `0` means every discovered frame succeeded or was
explicitly skipped and required artifacts were written. Invalid input, video
extraction failures, analyzer initialization failures, progress/output failures,
unresolved frame failures, and interruptions return nonzero statuses.

## Development

The core test suite uses local fixtures, fake analyzers, and mocks. It does not
download models, use a GPU, access the network, or require API credentials:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile identify_clearest_frames.py
python3 identify_clearest_frames.py --help
```

Optional real-FFmpeg integration tests are disabled by default. Run them with
`RUN_FFMPEG_INTEGRATION=1` when `ffmpeg` and `ffprobe` are installed. They do
not require model downloads, GPU hardware, API credentials, or network access.

Changes to file discovery, scoring, progress persistence, response parsing, or
copying behavior should add tests before relying on live model/API runs. Optional
CLIP/OpenAI smoke tests may require model downloads, hardware, credentials, or
network access, but are not part of the default test command.

## OpenSpec Workflow

OpenSpec is initialized with the `spec-driven` schema. Project-wide context and
engineering constraints live in `openspec/config.yaml`. Durable behavior
requirements belong in `openspec/specs/`; proposed work belongs in
`openspec/changes/`.

The generated OpenCode commands provide the normal workflow:

1. Explore the repository with `/opsx-explore`.
2. Propose a non-trivial change with `/opsx-propose`.
3. Implement its tasks with `/opsx-apply`.
4. Sync durable requirements with `/opsx-sync`.
5. Archive completed work with `/opsx-archive`.

See `CONTRIBUTING.md` for repository conventions and verification expectations.
