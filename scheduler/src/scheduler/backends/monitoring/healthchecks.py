import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from scheduler.backends.monitoring.base import JobMonitor

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 3


class HealthchecksMonitor(JobMonitor):
    """Healthchecks.io adapter for job lifecycle pings."""

    def __init__(
        self,
        ping_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._ping_url = ping_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

    def start(self) -> None:
        self._ping(f"{self._ping_url}/start")

    def success(self) -> None:
        self._ping(self._ping_url)

    def fail(self) -> None:
        self._ping(f"{self._ping_url}/fail")

    def _ping(self, url: str) -> None:
        for attempt in range(1, self._max_retries + 1):
            try:
                with urlopen(Request(url, method="GET"), timeout=self._timeout):
                    return
            except (URLError, ValueError) as exc:
                if attempt == self._max_retries:
                    logger.warning("Healthchecks ping failed after %d attempts: %s", attempt, exc)
                else:
                    logger.debug("Healthchecks ping attempt %d failed: %s", attempt, exc)
