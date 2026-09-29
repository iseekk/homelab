from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def upload(self, local_path: Path, remote_name: str) -> None:
        """Upload `local_path` to the remote backend under the name `remote_name`."""
