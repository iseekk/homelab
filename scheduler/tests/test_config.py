import pytest
from pydantic import ValidationError

from scheduler.config import Config


def test_healthchecks_ping_url_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({"healthchecks_ping_url": "not-a-url"})


def test_healthchecks_ping_url_accepts_valid_url() -> None:
    config = Config.model_validate({"healthchecks_ping_url": "https://hc-ping.com/uuid"})

    assert config.healthchecks_ping_url is not None
    assert str(config.healthchecks_ping_url).startswith("https://hc-ping.com/uuid")


def test_healthchecks_ping_url_empty_string_is_none() -> None:
    config = Config.model_validate({"healthchecks_ping_url": ""})

    assert config.healthchecks_ping_url is None
