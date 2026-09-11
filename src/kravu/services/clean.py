"""CleanWorkspace: reset the workspace so the pipeline can be re-run from scratch.

"Clean" means: clear every job from the blackboard, delete generated artifacts
(tailored resumes and cover letters), and truncate the log file. It deliberately
leaves setup untouched — ``profile.json``, ``searches.yaml``, and ``.env`` are the
user's configuration, not run output, so they survive a clean.

The use case holds the definition of what a clean removes; the entrypoint layer
owns the Y/N confirmation and the rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kravu import config


class _Clearable(Protocol):
    """The single store capability CleanWorkspace needs."""

    def clear_all(self) -> int:
        """Delete every job row; return the number removed."""
        ...


@dataclass(frozen=True, slots=True)
class CleanResult:
    """What a clean removed, for the caller to report back to the user."""

    jobs_removed: int
    files_removed: int


class CleanWorkspace:
    """Reset job state and generated artifacts. Idempotent and setup-preserving."""

    def run(self, store: _Clearable) -> CleanResult:
        """Clear jobs, remove artifacts, and truncate the log.

        Args:
            store: The job store to clear (its ``clear_all`` is the only method used).

        Returns:
            A ``CleanResult`` with the number of jobs and artifact files removed.
        """
        jobs_removed = store.clear_all()
        files_removed = self._remove_artifacts()
        self._truncate_log()
        return CleanResult(jobs_removed=jobs_removed, files_removed=files_removed)

    def _remove_artifacts(self) -> int:
        """Delete every file in the tailored-resume and cover-letter directories."""
        removed = 0
        for directory in (config.tailored_dir(), config.cover_dir()):
            if not directory.exists():
                continue
            for path in directory.iterdir():
                if path.is_file():
                    path.unlink()
                    removed += 1
        return removed

    def _truncate_log(self) -> None:
        """Empty the log file if it exists, leaving the file in place."""
        log_file: Path = config.log_dir() / "kravu.log"
        if log_file.exists():
            log_file.write_text("", encoding="utf-8")
