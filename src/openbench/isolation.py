"""Environment isolation utilities for agent runs."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def isolated_workdir() -> Iterator[Path]:
    """Create a fresh temporary directory for agent execution.

    The directory is automatically cleaned up when the context manager exits,
    regardless of whether the agent run succeeded or failed.

    Yields:
        Path to the isolated working directory.

    Example::

        with isolated_workdir() as workdir:
            # run agent with cwd=workdir
            ...
        # directory is deleted here
    """
    with tempfile.TemporaryDirectory(prefix="openbench_") as tmpdir:
        yield Path(tmpdir)
