from unittest.mock import MagicMock
from urllib.error import URLError

import pytest
from pytest_mock import MockerFixture

from scheduler.backends.monitoring.healthchecks import HealthchecksMonitor


@pytest.fixture
def mock_urlopen(mocker: MockerFixture) -> MagicMock:
    mock_response = mocker.MagicMock()
    mock_response.__enter__ = mocker.Mock(return_value=mock_response)
    mock_response.__exit__ = mocker.Mock(return_value=False)
    return mocker.patch(
        "scheduler.backends.monitoring.healthchecks.urlopen",
        return_value=mock_response,
    )


@pytest.mark.parametrize(
    ("method", "expected_url"),
    [
        ("start", "https://hc-ping.com/uuid/start"),
        ("success", "https://hc-ping.com/uuid"),
        ("fail", "https://hc-ping.com/uuid/fail"),
    ],
)
def test_ping_urls(mock_urlopen: MagicMock, method: str, expected_url: str) -> None:
    monitor = HealthchecksMonitor("https://hc-ping.com/uuid/")
    getattr(monitor, method)()

    request = mock_urlopen.call_args[0][0]
    assert request.full_url == expected_url


def test_ping_strips_trailing_slash_from_base_url(mock_urlopen: MagicMock) -> None:
    monitor = HealthchecksMonitor("https://hc-ping.com/uuid/")
    monitor.success()

    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "https://hc-ping.com/uuid"


def test_ping_retries_on_failure(mocker: MockerFixture) -> None:
    mock_urlopen = mocker.patch(
        "scheduler.backends.monitoring.healthchecks.urlopen",
        side_effect=URLError("network down"),
    )

    monitor = HealthchecksMonitor("https://hc-ping.com/uuid", max_retries=3)
    monitor.start()

    assert mock_urlopen.call_count == 3


def test_ping_does_not_raise_on_failure(mocker: MockerFixture) -> None:
    mocker.patch(
        "scheduler.backends.monitoring.healthchecks.urlopen",
        side_effect=URLError("network down"),
    )

    monitor = HealthchecksMonitor("https://hc-ping.com/uuid")
    monitor.fail()
