import sqlite3
import tarfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

import py7zr
import pytest
from freezegun import freeze_time
from pydantic import SecretStr
from pytest_mock import MockerFixture

from scheduler.backup.backup import (
    BackupConfig,
    VaultwardenArchiver,
    get_retention_sub_dirs,
    run_backup,
)

FROZEN_NOW = "2026-06-12 12:00:00"  # Wednesday, 3rd day of month
FROZEN_DT = datetime(2026, 6, 12, 12, 0, 0)
NOW_STR = "2025-06-12-1200"


def make_config(tmp_path: Path, **overrides: object) -> BackupConfig:
    fields: dict[str, object] = {
        "data_dir": tmp_path / "data",
        "local_backup_dir": tmp_path / "backups",
    }
    fields.update(overrides)
    return BackupConfig.model_construct(**fields)  # type: ignore[arg-type]


def make_archiver(tmp_path: Path, **config_overrides: object) -> VaultwardenArchiver:
    config = make_config(tmp_path, **config_overrides)
    return VaultwardenArchiver(config=config, now=FROZEN_DT)


# -- get_retention_sub_dirs --


@pytest.mark.parametrize(
    "now,include_extended,expected",
    [
        # include_extended=False always → only daily
        (datetime(2026, 6, 1, 12, 0), False, ["daily"]),
        # Wednesday, 3rd → no extra dirs
        (datetime(2026, 6, 3, 12, 0), True, ["daily"]),
        # Monday (weekday=0), not 1st → weekly
        (datetime(2026, 6, 8, 12, 0), True, ["daily", "weekly"]),
        # 1st of month, not Monday (Wednesday) → monthly
        (datetime(2026, 7, 1, 12, 0), True, ["daily", "monthly"]),
        # Monday AND 1st → both
        (datetime(2026, 6, 1, 12, 0), True, ["daily", "weekly", "monthly"]),
    ],
)
def test_get_retention_sub_dirs(now: datetime, include_extended: bool, expected: list[str]) -> None:
    assert get_retention_sub_dirs(now, include_extended) == expected


# -- VaultwardenArchiver.backup_sqlite --


def test_backup_sqlite_skips_when_missing(tmp_path: Path) -> None:
    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    archiver.backup_sqlite(temp_dir)
    assert list(temp_dir.iterdir()) == []


def test_backup_sqlite_creates_valid_db(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "db.sqlite3"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.commit()

    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    archiver.backup_sqlite(temp_dir)

    results = list(temp_dir.glob("db.*.sqlite3"))
    assert len(results) == 1
    with closing(sqlite3.connect(results[0])) as conn:
        conn.execute("SELECT * FROM t")  # no exception → valid DB


# -- VaultwardenArchiver.backup_config --


def test_backup_config_skips_when_missing(tmp_path: Path) -> None:
    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    archiver.backup_config(temp_dir)
    assert list(temp_dir.iterdir()) == []


def test_backup_config_copies_file(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.json").write_text('{"key": "value"}')

    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    archiver.backup_config(temp_dir)

    results = list(temp_dir.glob("config.*.json"))
    assert len(results) == 1
    assert results[0].read_text() == '{"key": "value"}'


# -- VaultwardenArchiver.backup_rsakey --


def test_backup_rsakey_skips_when_missing(tmp_path: Path) -> None:
    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    archiver.backup_rsakey(temp_dir)
    assert list(temp_dir.iterdir()) == []


def test_backup_rsakey_archives_matching_files(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "rsa_key.pem").write_bytes(b"pem")
    (data_dir / "rsa_key.pub.pem").write_bytes(b"pub")
    (data_dir / "unrelated.txt").write_bytes(b"nope")

    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    archiver.backup_rsakey(temp_dir)

    results = list(temp_dir.glob("rsakey.*.tar"))
    assert len(results) == 1
    with tarfile.open(results[0]) as tar:
        names = tar.getnames()
    assert sorted(names) == ["rsa_key.pem", "rsa_key.pub.pem"]


# -- VaultwardenArchiver.backup_directory --


def test_backup_directory_skips_when_missing(tmp_path: Path) -> None:
    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    archiver.backup_directory(source=tmp_path / "nonexistent", label="attachments", temp_dir=temp_dir)
    assert list(temp_dir.iterdir()) == []


def test_backup_directory_creates_tar(tmp_path: Path) -> None:
    source = tmp_path / "attachments"
    source.mkdir()
    (source / "file.txt").write_bytes(b"data")

    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    archiver.backup_directory(source=source, label="attachments", temp_dir=temp_dir)

    results = list(temp_dir.glob("attachments.*.tar"))
    assert len(results) == 1


# -- VaultwardenArchiver.package --


def test_package_returns_none_when_empty(tmp_path: Path) -> None:
    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    assert archiver.package(temp_dir) is None


def test_package_creates_archive_without_password(tmp_path: Path) -> None:
    archiver = make_archiver(tmp_path)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    (temp_dir / "file.txt").write_bytes(b"hello")

    result = archiver.package(temp_dir)

    assert result is not None
    assert result.suffix == ".7z"
    with py7zr.SevenZipFile(result, mode="r") as archive:
        assert "file.txt" in archive.getnames()


def test_package_creates_encrypted_archive(tmp_path: Path) -> None:
    archiver = make_archiver(tmp_path, archive_password=SecretStr("secret"))
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    (temp_dir / "file.txt").write_bytes(b"hello")

    result = archiver.package(temp_dir)

    assert result is not None
    with py7zr.SevenZipFile(result, mode="r", password="secret") as archive:
        assert "file.txt" in archive.getnames()


# -- run_backup --


@freeze_time(FROZEN_NOW)
def test_run_backup_raises_when_data_dir_missing(mocker: MockerFixture, tmp_path: Path) -> None:
    config = make_config(tmp_path)  # data_dir not created
    backend = mocker.MagicMock()
    with pytest.raises(FileNotFoundError, match="Data directory does not exist"):
        run_backup(config, backend, include_extended=False)


@freeze_time("2026-06-01 12:00:00")  # Monday AND 1st of month → daily + weekly + monthly
def test_run_backup_uploads_for_each_sub_dir(mocker: MockerFixture, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "db.sqlite3").write_bytes(b"")

    config = make_config(tmp_path, archive_password=None)
    backend = mocker.MagicMock()

    run_backup(config, backend, include_extended=True)

    call_remote_names = [call.kwargs["remote_name"] for call in backend.upload.call_args_list]
    assert any(n.startswith("daily/") for n in call_remote_names)
    assert any(n.startswith("weekly/") for n in call_remote_names)
    assert any(n.startswith("monthly/") for n in call_remote_names)


@freeze_time(FROZEN_NOW)
def test_run_backup_no_upload_when_nothing_collected(mocker: MockerFixture, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # no files → package returns None

    config = make_config(tmp_path)
    backend = mocker.MagicMock()

    run_backup(config, backend, include_extended=False)

    backend.upload.assert_not_called()
