"""Checksum helper for the ingest pipeline (`Connector.run`: fetch -> hash ->
parse -> validate -> manifest).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """Deterministic ID for entities with no natural key (e.g. an Officer
    identified only by name, or a LEIE row with no stable row ID).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
