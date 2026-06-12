from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from scheduler.main import main, schedule_backup_jobs


@pytest.fixture
def mock_config(mocker: MockerFixture) -> MagicMock:
    mock_cls = mocker.patch("scheduler.main.BackupConfig")
    config: MagicMock = mock_cls.return_value
    config.s3_bucket = None
    config.local_backup_dir = "/tmp/backups"
    config.resolved_backup_times = ["02:00"]
    return config


# -- schedule_backup_jobs --


def test_schedule_backup_jobs_raises_without_credentials(mock_config: MagicMock) -> None:
    mock_config.s3_bucket = "my-bucket"
    mock_config.aws_access_key_id = None
    mock_config.aws_secret_access_key = None
    with pytest.raises(ValueError, match="AWS credentials must be provided when using S3 backend"):
        schedule_backup_jobs()


def test_schedule_backup_jobs_uses_s3_backend(mock_config: MagicMock, mocker: MockerFixture) -> None:
    mock_config.s3_bucket = "my-bucket"
    mock_config.aws_access_key_id = "KEY"
    mock_config.aws_secret_access_key.get_secret_value.return_value = "SECRET"
    mock_s3 = mocker.patch("scheduler.main.S3Backend")
    mocker.patch("scheduler.main.schedule")

    schedule_backup_jobs()

    mock_s3.assert_called_once()


def test_schedule_backup_jobs_uses_local_backend(mock_config: MagicMock, mocker: MockerFixture) -> None:
    mock_local = mocker.patch("scheduler.main.LocalFilesystemBackend")
    mocker.patch("scheduler.main.schedule")

    schedule_backup_jobs()

    mock_local.assert_called_once()


def test_schedule_backup_jobs_schedules_one_job_per_time(mock_config: MagicMock, mocker: MockerFixture) -> None:
    mock_config.resolved_backup_times = ["02:00", "06:00", "14:00"]
    mocker.patch("scheduler.main.LocalFilesystemBackend")
    mock_schedule = mocker.patch("scheduler.main.schedule")

    schedule_backup_jobs()

    assert mock_schedule.every.return_value.day.at.return_value.do.call_count == 3


def test_schedule_backup_jobs_first_job_has_extended_retention(mock_config: MagicMock, mocker: MockerFixture) -> None:
    # sorted: 02:00 first → include_extended=True; 06:00, 14:00 → False
    mock_config.resolved_backup_times = ["06:00", "02:00", "14:00"]
    mocker.patch("scheduler.main.LocalFilesystemBackend")
    mock_schedule = mocker.patch("scheduler.main.schedule")

    schedule_backup_jobs()

    do_calls = mock_schedule.every.return_value.day.at.return_value.do.call_args_list
    extended_flags = [call.kwargs["include_extended"] for call in do_calls]
    assert extended_flags.count(True) == 1
    assert extended_flags.count(False) == 2


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
