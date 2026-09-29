from pathlib import Path
from unittest.mock import MagicMock

import pytest
import schedule
from pydantic import SecretStr
from pytest_mock import MockerFixture

from scheduler.backends.monitoring.healthchecks import HealthchecksMonitor
from scheduler.backup.config import BackupConfig
from scheduler.main import create_job_monitor, create_storage, main, schedule_backup_jobs


def make_config(**overrides: object) -> BackupConfig:
    fields: dict[str, object] = {
        "local_backup_dir": Path("/tmp/backups"),
    }
    fields.update(overrides)
    return BackupConfig.model_construct(**fields)  # type: ignore[arg-type]


@pytest.fixture
def mock_config(mocker: MockerFixture) -> MagicMock:
    mock_cls = mocker.patch("scheduler.main.BackupConfig")
    config: MagicMock = mock_cls.return_value
    config.s3_bucket = None
    config.local_backup_dir = "/tmp/backups"
    config.resolved_backup_times = ["02:00"]
    return config


# -- create_storage --


def test_create_storage_raises_without_credentials() -> None:
    config = make_config(
        s3_bucket="my-bucket",
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )
    with pytest.raises(ValueError, match="AWS credentials must be provided when using S3 storage"):
        create_storage(config)


def test_create_storage_uses_s3(mocker: MockerFixture) -> None:
    config = make_config(
        s3_bucket="my-bucket",
        s3_prefix="vaultwarden",
        s3_region="eu-central-1",
        aws_access_key_id="KEY",
        aws_secret_access_key=SecretStr("SECRET"),
    )
    mock_s3 = mocker.patch("scheduler.main.S3Storage")

    create_storage(config)

    mock_s3.assert_called_once_with(
        bucket="my-bucket",
        prefix="vaultwarden",
        region="eu-central-1",
        access_key_id="KEY",
        secret_access_key="SECRET",
    )


def test_create_storage_uses_local(mocker: MockerFixture) -> None:
    config = make_config(local_backup_dir=Path("/tmp/backups"))
    mock_local = mocker.patch("scheduler.main.LocalFilesystemStorage")

    create_storage(config)

    mock_local.assert_called_once_with(remote_dir=Path("/tmp/backups"))


# -- create_job_monitor --


def test_create_job_monitor_uses_healthchecks(mocker: MockerFixture) -> None:
    config = BackupConfig.model_validate({"healthchecks_ping_url": "https://hc-ping.com/uuid"})
    mock_healthchecks = mocker.patch("scheduler.main.HealthchecksMonitor")

    create_job_monitor(config)

    mock_healthchecks.assert_called_once_with("https://hc-ping.com/uuid")


def test_create_job_monitor_uses_noop(mocker: MockerFixture) -> None:
    config = make_config(healthchecks_ping_url=None)
    mock_noop = mocker.patch("scheduler.main.NoopMonitor")

    create_job_monitor(config)

    mock_noop.assert_called_once()


# -- schedule_backup_jobs --


def test_schedule_backup_jobs_creates_storage_and_monitor(mock_config: MagicMock, mocker: MockerFixture) -> None:
    mock_create_storage = mocker.patch("scheduler.main.create_storage")
    mock_create_monitor = mocker.patch("scheduler.main.create_job_monitor")
    mocker.patch("scheduler.main.schedule")

    schedule_backup_jobs()

    mock_create_storage.assert_called_once_with(mock_config)
    mock_create_monitor.assert_called_once_with(mock_config)


def test_schedule_backup_jobs_schedules_one_job_per_time(mock_config: MagicMock, mocker: MockerFixture) -> None:
    mock_config.resolved_backup_times = ["02:00", "06:00", "14:00"]
    mocker.patch("scheduler.main.create_storage")
    mocker.patch("scheduler.main.create_job_monitor")
    mock_schedule = mocker.patch("scheduler.main.schedule")

    schedule_backup_jobs()

    assert mock_schedule.every.return_value.day.at.return_value.do.call_count == 3


def test_schedule_backup_jobs_first_job_has_extended_retention(mock_config: MagicMock, mocker: MockerFixture) -> None:
    # sorted: 02:00 first → include_extended=True; 06:00, 14:00 → False
    mock_config.resolved_backup_times = ["06:00", "02:00", "14:00"]
    mocker.patch("scheduler.main.create_storage")
    mocker.patch("scheduler.main.create_job_monitor")
    mock_schedule = mocker.patch("scheduler.main.schedule")

    schedule_backup_jobs()

    do_calls = mock_schedule.every.return_value.day.at.return_value.do.call_args_list
    extended_flags = [call.kwargs["include_extended"] for call in do_calls]
    assert extended_flags.count(True) == 1
    assert extended_flags.count(False) == 2


def test_job_runs_backup_when_healthchecks_ping_raises_value_error(
    mocker: MockerFixture, mock_config: MagicMock
) -> None:
    mocker.patch("scheduler.main.create_storage")
    mock_run_backup = mocker.patch("scheduler.main.run_backup")
    mocker.patch(
        "scheduler.backends.monitoring.healthchecks.urlopen",
        side_effect=ValueError("invalid URL"),
    )
    mocker.patch(
        "scheduler.main.create_job_monitor",
        return_value=HealthchecksMonitor("https://hc-ping.com/uuid"),
    )
    schedule.clear()

    schedule_backup_jobs()
    schedule.run_all()

    mock_run_backup.assert_called_once()


def test_job_signals_success(mocker: MockerFixture, mock_config: MagicMock) -> None:
    mocker.patch("scheduler.main.create_storage")
    mocker.patch("scheduler.main.run_backup")
    mock_monitor = mocker.MagicMock()
    mocker.patch("scheduler.main.create_job_monitor", return_value=mock_monitor)
    schedule.clear()

    schedule_backup_jobs()
    schedule.run_all()

    mock_monitor.start.assert_called_once()
    mock_monitor.success.assert_called_once()
    mock_monitor.fail.assert_not_called()


def test_job_signals_failure(mocker: MockerFixture, mock_config: MagicMock) -> None:
    mocker.patch("scheduler.main.create_storage")
    mocker.patch("scheduler.main.run_backup", side_effect=RuntimeError("boom"))
    mock_monitor = mocker.MagicMock()
    mocker.patch("scheduler.main.create_job_monitor", return_value=mock_monitor)
    schedule.clear()

    schedule_backup_jobs()
    schedule.run_all()

    mock_monitor.start.assert_called_once()
    mock_monitor.fail.assert_called_once()
    mock_monitor.success.assert_not_called()


# -- main --


def test_main_calls_setup_logging_and_schedule(mocker: MockerFixture) -> None:
    mock_setup = mocker.patch("scheduler.main.setup_logging")
    mock_schedule_jobs = mocker.patch("scheduler.main.schedule_backup_jobs")
    mock_schedule = mocker.patch("scheduler.main.schedule")
    mock_schedule.idle_seconds.return_value = None

    main()

    mock_setup.assert_called_once()
    mock_schedule_jobs.assert_called_once()


def test_main_exits_when_no_jobs_scheduled(mocker: MockerFixture) -> None:
    mocker.patch("scheduler.main.setup_logging")
    mocker.patch("scheduler.main.schedule_backup_jobs")
    mock_schedule = mocker.patch("scheduler.main.schedule")
    mock_schedule.idle_seconds.return_value = None

    main()  # must not hang
