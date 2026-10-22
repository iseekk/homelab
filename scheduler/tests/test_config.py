import pytest
from pydantic import ValidationError

from scheduler.config import Config

VALID = {"archive_password": "x" * 14}


def test_archive_password_is_required() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({})


def test_archive_password_rejects_13_characters() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({"archive_password": "x" * 13})


def test_archive_password_accepts_14_characters() -> None:
    assert Config.model_validate({"archive_password": "x" * 14}).archive_password.get_secret_value() == "x" * 14


def test_healthchecks_ping_url_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({**VALID, "healthchecks_ping_url": "not-a-url"})


def test_healthchecks_ping_url_accepts_valid_url() -> None:
    config = Config.model_validate({**VALID, "healthchecks_ping_url": "https://hc-ping.com/uuid"})

    assert config.healthchecks_ping_url is not None
    assert str(config.healthchecks_ping_url).startswith("https://hc-ping.com/uuid")


def test_healthchecks_ping_url_empty_string_is_none() -> None:
    config = Config.model_validate({**VALID, "healthchecks_ping_url": ""})

    assert config.healthchecks_ping_url is None
