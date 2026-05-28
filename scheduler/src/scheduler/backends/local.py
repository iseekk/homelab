import logging
import shutil
from pathlib import Path

from scheduler.backends.base import StorageBackend

logger = logging.getLogger(__name__)


class LocalFilesystemBackend(StorageBackend):
    """Simple local filesystem backend."""

    def __init__(self, remote_dir: Path) -> None:
        self.remote_dir = remote_dir
        self.remote_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: Path, remote_name: str) -> None:
        destination = self.remote_dir / remote_name
        if not destination.parent.is_dir():
            destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        logger.info("File '%s' copied to '%s'", local_path.name, destination)
