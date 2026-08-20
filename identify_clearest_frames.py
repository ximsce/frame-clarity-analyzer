#!/usr/bin/env python3
"""Compatibility wrapper for the Frame Clarity Analyzer CLI."""

from frame_clarity.cli import main, process_frames
from frame_clarity.discovery import configured_prefix


FRAME_PREFIX = configured_prefix()


if __name__ == "__main__":
    raise SystemExit(main())
