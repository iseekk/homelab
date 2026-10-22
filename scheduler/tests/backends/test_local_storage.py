import os
import time
from pathlib import Path

from scheduler.backends.storage.local import LocalFilesystemStorage

# -- __init__ --


def test_init_creates_remote_dir(tmp_path: Path) -> None:
    remote_dir = tmp_path / "a" / "b" / "c"
    LocalFilesystemStorage(remote_dir)
    assert remote_dir.is_dir()


# -- upload --


def test_upload_copies_file(tmp_path: Path) -> None:
    src = tmp_path / "backup.7z"
    src.write_bytes(b"data")
    remote_dir = tmp_path / "remote"

    storage = LocalFilesystemStorage(remote_dir)
    storage.upload(src, "backup.7z")

    assert (remote_dir / "backup.7z").read_bytes() == b"data"


def test_upload_creates_subdirectory(tmp_path: Path) -> None:
    src = tmp_path / "backup.7z"
    src.write_bytes(b"data")
    remote_dir = tmp_path / "remote"

    storage = LocalFilesystemStorage(remote_dir)
    storage.upload(src, "daily/backup.7z")

    assert (remote_dir / "daily" / "backup.7z").read_bytes() == b"data"


def test_upload_overwrites_existing_file(tmp_path: Path) -> None:
    src = tmp_path / "backup.7z"
    src.write_bytes(b"new")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / "backup.7z").write_bytes(b"old")

    storage = LocalFilesystemStorage(remote_dir)
    storage.upload(src, "backup.7z")

    assert (remote_dir / "backup.7z").read_bytes() == b"new"


# -- retention --


def _age(path: Path, days: int) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def _upload(storage: LocalFilesystemStorage, tmp_path: Path, name: str) -> None:
    src = tmp_path / name
    src.write_bytes(b"data")
    storage.upload(src, f"daily/{name}")


def test_upload_prunes_files_older_than_retention(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path / "remote", retention_days={"daily": 7})
    _upload(storage, tmp_path, "old.7z")
    _age(tmp_path / "remote" / "daily" / "old.7z", 8)
    _upload(storage, tmp_path, "recent.7z")
    _age(tmp_path / "remote" / "daily" / "recent.7z", 6)

    _upload(storage, tmp_path, "new.7z")

    assert sorted(f.name for f in (tmp_path / "remote" / "daily").iterdir()) == ["new.7z", "recent.7z"]


def test_upload_keeps_newest_file_even_when_older_than_retention(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path / "remote", retention_days={"daily": 7})
    src = tmp_path / "a.7z"
    src.write_bytes(b"data")
    _age(src, 30)  # copy2 keeps the old mtime, so the only file in daily looks expired

    storage.upload(src, "daily/a.7z")

    assert (tmp_path / "remote" / "daily" / "a.7z").exists()


def test_upload_prunes_only_configured_tier(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path / "remote", retention_days={"daily": 7})
    weekly = tmp_path / "remote" / "weekly"
    weekly.mkdir(parents=True)
    (weekly / "old.7z").write_bytes(b"x")
    _age(weekly / "old.7z", 100)

    src = tmp_path / "new.7z"
    src.write_bytes(b"data")
    storage.upload(src, "weekly/new.7z")

    assert (weekly / "old.7z").exists()
