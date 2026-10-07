from abc import ABC, abstractmethod


class Monitor(ABC):
    """Port for signaling events to an external monitoring service (e.g. heartbeats, job runs)."""

    @abstractmethod
    def start(self) -> None:
        """Signal that a monitored period or task has started."""

    @abstractmethod
    def success(self) -> None:
        """Signal success — a heartbeat or completed task."""

    @abstractmethod
    def fail(self) -> None:
        """Signal that a monitored period or task failed."""
