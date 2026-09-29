from abc import ABC, abstractmethod


class JobMonitor(ABC):
    """Port for signaling job lifecycle events to an external monitoring service."""

    @abstractmethod
    def start(self) -> None:
        """Signal that a job run has started."""

    @abstractmethod
    def success(self) -> None:
        """Signal that a job run completed successfully."""

    @abstractmethod
    def fail(self) -> None:
        """Signal that a job run failed."""
