"""Small atomic JSON storage primitives shared by progress and results."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Type


def atomic_write_json(path: Path, payload: Any, error_type: Type[Exception]) -> None:
    """Publish JSON by replacing the destination only after a complete write."""

    destination = Path(path)
    parent = destination.parent
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".%s." % destination.name,
            suffix=".tmp",
            dir=str(parent),
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(destination))
        temporary = None
    except (OSError, TypeError, ValueError) as exc:
        raise error_type("Could not write %s: %s" % (destination, exc)) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def read_json(path: Path, error_type: Type[Exception]) -> Any:
    destination = Path(path)
    try:
        with destination.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise error_type("Could not read %s: %s" % (destination, exc)) from exc
