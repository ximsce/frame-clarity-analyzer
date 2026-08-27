"""Frame filename validation, ordering, and input identity."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import List, Mapping, Optional

from .errors import ConfigurationError, DiscoveryError
from .models import FrameManifest, FrameManifestItem, FrameProvenance


DEFAULT_FRAME_PREFIX = "rawFrames"


def configured_prefix(prefix: Optional[str] = None) -> str:
    value = prefix if prefix is not None else os.getenv("FRAME_PREFIX", DEFAULT_FRAME_PREFIX)
    if not value:
        raise ConfigurationError("FRAME_PREFIX must not be empty")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DiscoveryError("Could not read frame %s: %s" % (path.name, exc)) from exc
    return digest.hexdigest()


def discover_frames(
    frames_dir: Path,
    prefix: Optional[str] = None,
    provenance_by_filename: Optional[Mapping[str, FrameProvenance]] = None,
    identity_context: Optional[str] = None,
) -> FrameManifest:
    """Return a validated numeric manifest for a PNG frame directory."""

    directory = Path(frames_dir)
    if not directory.exists():
        raise DiscoveryError("Frames directory does not exist: %s" % directory)
    if not directory.is_dir():
        raise DiscoveryError("Frames path is not a directory: %s" % directory)

    frame_prefix = configured_prefix(prefix)
    pattern = re.compile(r"^%s(\d+)$" % re.escape(frame_prefix))
    png_files = sorted(
        (entry for entry in directory.iterdir() if entry.is_file() and entry.suffix == ".png"),
        key=lambda entry: entry.name,
    )
    if not png_files:
        raise DiscoveryError("No PNG frames found in %s" % directory)

    invalid = [entry.name for entry in png_files if pattern.fullmatch(entry.stem) is None]
    if invalid:
        raise DiscoveryError(
            "Invalid frame filename(s) in %s (expected %s<number>.png): %s"
            % (directory, frame_prefix, ", ".join(invalid))
        )

    if provenance_by_filename:
        unknown_provenance = set(provenance_by_filename).difference(entry.name for entry in png_files)
        if unknown_provenance:
            raise DiscoveryError(
                "Provenance contains unknown frame(s): %s"
                % ", ".join(sorted(unknown_provenance))
            )

    items: List[FrameManifestItem] = []
    seen_indices = {}
    for entry in png_files:
        match = pattern.fullmatch(entry.stem)
        assert match is not None
        frame_index = int(match.group(1))
        if frame_index in seen_indices:
            raise DiscoveryError(
                "Duplicate frame number %s in %s and %s"
                % (frame_index, seen_indices[frame_index], entry.name)
            )
        seen_indices[frame_index] = entry.name
        try:
            stat = entry.stat()
        except OSError as exc:
            raise DiscoveryError("Could not inspect frame %s: %s" % (entry.name, exc)) from exc
        items.append(
            FrameManifestItem(
                filename=entry.name,
                path=entry.resolve(),
                frame_index=frame_index,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256=_file_sha256(entry),
                provenance=(provenance_by_filename or {}).get(entry.name),
            )
        )

    items.sort(key=lambda item: item.frame_index)
    identity = hashlib.sha256()
    if identity_context:
        identity.update(("context\0%s\n" % identity_context).encode("utf-8"))
    for item in items:
        identity.update(
            ("%s\0%s\0%s\0%s\n" % (item.filename, item.frame_index, item.size, item.sha256)).encode(
                "utf-8"
            )
        )
        if item.provenance is not None:
            identity.update(
                ("provenance\0%s\n" % json.dumps(
                    item.provenance.to_dict(), sort_keys=True, separators=(",", ":")
                )).encode("utf-8")
            )
    return FrameManifest(
        directory=directory.resolve(),
        prefix=frame_prefix,
        items=tuple(items),
        input_id=identity.hexdigest(),
    )
