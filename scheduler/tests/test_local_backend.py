from pathlib import Path

from scheduler.backends.local import LocalFilesystemBackend

# -- __init__ --


def test_init_creates_remote_dir(tmp_path: Path) -> None:
    remote_dir = tmp_path / "a" / "b" / "c"
    LocalFilesystemBackend(remote_dir)
    assert remote_dir.is_dir()


# -- upload --


def test_upload_copies_file(tmp_path: Path) -> None:
    src = tmp_path / "backup.7z"
    src.write_bytes(b"data")
    remote_dir = tmp_path / "remote"

    backend = LocalFilesystemBackend(remote_dir)
    backend.upload(src, "backup.7z")

    assert (remote_dir / "backup.7z").read_bytes() == b"data"


def test_upload_creates_subdirectory(tmp_path: Path) -> None:
    src = tmp_path / "backup.7z"
    src.write_bytes(b"data")
    remote_dir = tmp_path / "remote"

    backend = LocalFilesystemBackend(remote_dir)
    backend.upload(src, "daily/backup.7z")

    assert (remote_dir / "daily" / "backup.7z").read_bytes() == b"data"


def test_upload_overwrites_existing_file(tmp_path: Path) -> None:
    src = tmp_path / "backup.7z"
    src.write_bytes(b"new")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / "backup.7z").write_bytes(b"old")

    backend = LocalFilesystemBackend(remote_dir)
    backend.upload(src, "backup.7z")

    assert (remote_dir / "backup.7z").read_bytes() == b"new"
