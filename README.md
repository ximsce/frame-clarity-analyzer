# Frame Clarity Analyzer

Script to identify the clearest frames from a directory of video frame images using either:

- a **local CLIP model** (default, free once downloaded), or
- the **OpenAI Vision API** (optional, requires API key and credits).

## Requirements

- Python 3.9+ (tested locally with 3.9)
- For CLIP (default analyzer):
  - `torch`
  - `transformers`
  - `pillow`
- For OpenAI Vision (optional):
  - `openai`

Install dependencies (example):

```bash
pip install torch transformers pillow openai
```

## Usage

Run from the project root:

```bash
python identify_clearest_frames.py --frames-dir rawFrames
```

Key options:

- `--frames-dir`: directory containing `.png` frame images (default: `rawFrames`)
- `--output-dir`: where to copy the top N clearest frames (default: `clearest_frames` next to `frames-dir`)
- `--batch-size`: frames per batch (default: 10)
- `--top-n`: how many top frames to save (default: 50)
- `--analyzer`: `"clip"` (local, default) or `"openai"`
- `--api-key`: OpenAI API key when using `--analyzer openai` (or set `OPENAI_API_KEY`)

Example using OpenAI:

```bash
OPENAI_API_KEY=sk-... \
python identify_clearest_frames.py \
  --frames-dir rawFrames \
  --analyzer openai \
  --model gpt-4o
```

## Frame filename prefix

Frames are expected to follow a naming pattern like:

```text
rawFrames0001.png
rawFrames0002.png
...
```

The numeric part is used to sort frames. The prefix can be customized via the `FRAME_PREFIX` environment variable (default: `rawFrames`):

```bash
FRAME_PREFIX="myPrefix" python identify_clearest_frames.py --frames-dir myFrames
```

