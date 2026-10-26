"""Append-only JSON-array logs (usage, audit trail), carried over unchanged from HW6 (hw6-vendor-desk, tools.py)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOG_LOCK = threading.Lock()  # PydanticAI runs sync tools in worker threads; parallel calls share a file


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json_array(path: Path) -> list:
    """Entries of a JSON-array log; a missing or empty file counts as []. Raises if it isn't an array."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    entries = json.loads(text) if text.strip() else []
    if not isinstance(entries, list):
        raise ValueError(f"{path} must hold a JSON array; refusing to overwrite it")
    return entries


def ensure_json_array(path: Path) -> None:
    """Create the file as an empty JSON array if it does not exist yet."""
    with _LOG_LOCK:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(path, [])


def append_json(path: Path, record: dict) -> int:
    """Append one record to a JSON-array file, keeping every existing entry. Returns the new length."""
    with _LOG_LOCK:
        entries = read_json_array(path)
        entries.append(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(path, entries)
        return len(entries)


def _write_json(path: Path, data: list) -> None:
    """Write via a unique temporary file and an atomic rename, so a crash never leaves half a log."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
