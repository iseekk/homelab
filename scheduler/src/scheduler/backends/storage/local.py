import logging
import shutil
import time
from collections.abc import Mapping
from pathlib import Path

from scheduler.backends.storage.base import Storage

logger = logging.getLogger(__name__)


class LocalFilesystemStorage(Storage):
    """Local filesystem storage backend; prunes old files per subdirectory (e.g. `daily`) after each upload."""

    def __init__(self, remote_dir: Path, retention_days: Mapping[str, int] | None = None) -> None:
        self.remote_dir = remote_dir
        self.retention_days = retention_days or {}
        self.remote_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: Path, remote_name: str) -> None:
        destination = self.remote_dir / remote_name
        if not destination.parent.is_dir():
            destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        logger.info("File '%s' copied to '%s'", local_path.name, destination)
        self._prune(destination.parent)

    def _prune(self, directory: Path) -> None:
        days = self.retention_days.get(directory.name)
        if days is None:
            return
        cutoff = time.time() - days * 86400
        files = sorted((f for f in directory.iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime)
        for file in files[:-1]:  # the newest file is always kept
            if file.stat().st_mtime < cutoff:
                file.unlink()
                logger.info("Removed '%s' (older than %d days)", file, days)
