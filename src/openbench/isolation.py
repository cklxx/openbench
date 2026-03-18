"""Environment isolation utilities for agent runs."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _validate_setup_path(relative_path: str) -> None:
    """Reject paths that could escape the workdir."""
    p = Path(relative_path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(
            f"setup_files key {relative_path!r} must be a relative path with no '..' components."
        )


@contextmanager
def isolated_workdir(
    setup_files: dict[str, str] | None = None,
) -> Iterator[Path]:
    """Create a fresh temporary directory for agent execution.

    If *setup_files* is provided, each key-value pair is written as a file
    into the directory before yielding. Keys must be relative paths with no
    ``..`` components (directory traversal is rejected).

    The directory is automatically cleaned up when the context manager exits,
    regardless of whether the agent run succeeded or failed.

    Yields:
        Path to the isolated working directory.

    Example::

        with isolated_workdir(setup_files={"seed.py": "x = 1"}) as workdir:
            # run agent with cwd=workdir
            ...
        # directory is deleted here
    """
    with tempfile.TemporaryDirectory(prefix="openbench_") as tmpdir:
        workdir = Path(tmpdir)

        if setup_files:
            for rel_path, content in setup_files.items():
                _validate_setup_path(rel_path)
                dest = workdir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

        yield workdir
