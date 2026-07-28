"""Resolve runtime data directories for legal RAG persistence.

When the package is installed into site-packages (Docker runtime image), resolving
relative paths via ``Path(__file__).parents[N]`` points inside site-packages —
not the app WORKDIR / Docker volume. Prefer CWD (WORKDIR=/app) instead.
"""

from __future__ import annotations

from pathlib import Path


def resolve_runtime_data_path(configured: str | Path) -> Path:
    """Return an absolute path for a configured data directory.

    Absolute settings are used as-is. Relative settings resolve against process
    CWD so Docker volume mounts at ``/app/data/...`` are honored.
    """
    path = Path(configured)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()
