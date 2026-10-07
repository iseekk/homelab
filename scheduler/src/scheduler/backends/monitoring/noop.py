from scheduler.backends.monitoring.base import Monitor


class NoopMonitor(Monitor):
    """No-op monitor used when no external monitoring is configured."""

    def start(self) -> None:
        pass

    def success(self) -> None:
        pass

    def fail(self) -> None:
        pass
