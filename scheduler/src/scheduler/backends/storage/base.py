from abc import ABC, abstractmethod
from pathlib import Path


class Storage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def upload(self, local_path: Path, remote_name: str) -> None:
        """Upload `local_path` to the remote storage under the name `remote_name`."""
