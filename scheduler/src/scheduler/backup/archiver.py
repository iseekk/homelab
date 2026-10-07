import logging
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

import py7zr

from scheduler.backends.storage.base import Storage
from scheduler.config import Config

logger = logging.getLogger(__name__)


class VaultwardenArchiver:
    """Responsible for collecting Vaultwarden files and packaging them into a password-protected archive."""

    def __init__(self, config: Config, now: datetime) -> None:
        self.config = config
        self.now_str: str = now.strftime(config.backup_file_date_format)

    def backup_sqlite(self, temp_dir: Path) -> None:
        """SQLite backup using the native sqlite3.Connection.backup() method."""
        db_path = self.config.resolved_data_db
        if not db_path.exists():
            logger.info("SQLite database file does not exist: %s — skipping", db_path)
            return

        dest = temp_dir / f"db.{self.now_str}.sqlite3"

        logger.info("Creating SQLite backup: %s → %s", db_path, dest)
        with closing(sqlite3.connect(db_path, timeout=30)) as src_conn, closing(sqlite3.connect(dest)) as dst_conn:
            src_conn.backup(dst_conn)
        logger.info("SQLite backup completed successfully")

    def backup_config(self, temp_dir: Path) -> None:
        """Backup of the config.json configuration file."""
        config_path = self.config.resolved_data_config
        if not config_path.exists():
            logger.info("Configuration file does not exist: %s — skipping", config_path)
            return

        dest = temp_dir / f"config.{self.now_str}.json"
        shutil.copy2(src=config_path, dst=dest)
        logger.info("config.json copied to: %s", dest)

    def backup_rsakey(self, temp_dir: Path) -> None:
        """Archive RSA key files into a tar archive."""
        rsakey_path = self.config.resolved_data_rsakey
        parent = rsakey_path.parent
        prefix = rsakey_path.name

        matching = sorted(parent.glob(f"{prefix}*"))
        if not matching:
            logger.info("No RSA key files found with prefix: %s — skipping", rsakey_path)
            return

        dest = temp_dir / f"rsakey.{self.now_str}.tar"

        with tarfile.open(dest, "w") as tar:
            for key_file in matching:
                tar.add(key_file, arcname=key_file.name)
                logger.debug("Added to RSA archive: %s", key_file.name)

        logger.info("RSA keys archived to: %s (%d files)", dest, len(matching))

    def backup_directory(self, source: Path, label: str, temp_dir: Path) -> None:
        """General method for archiving a directory (attachments, sends) into a tar archive."""
        if not source.is_dir():
            logger.info("Directory '%s' does not exist: %s — skipping", label, source)
            return

        dest = temp_dir / f"{label}.{self.now_str}.tar"

        with tarfile.open(dest, "w") as tar:
            tar.add(source, arcname=source.name)

        logger.info("Directory '%s' archived to: %s", label, dest)

    def package(self, temp_dir: Path) -> Path | None:
        """Package files from temp_dir into a password-protected 7z archive with header encryption."""
        files_to_archive = list(temp_dir.iterdir())
        if not files_to_archive:
            logger.warning("No files to archive in temporary directory: %s — skipping archive creation", temp_dir)
            return None

        archive_path = temp_dir / f"backup.{self.now_str}.7z"
        password = self.config.archive_password.get_secret_value() if self.config.archive_password else None
        if not password:
            logger.warning("No archive password provided — creating unencrypted archive (not recommended)")
        with py7zr.SevenZipFile(
            file=archive_path,
            mode="w",
            password=password,
            header_encryption=password is not None,
        ) as archive:
            for file in files_to_archive:
                if file.is_file():
                    archive.write(file, arcname=file.name)
                    logger.debug("Added to 7z: %s", file.name)

        logger.info("7z archive ready: %s", archive_path)
        return archive_path


def get_retention_sub_dirs(now: datetime, include_extended: bool) -> list[str]:
    """Return retention subdirectories based on the current date and whether extended retention should be included."""
    dirs = ["daily"]

    if include_extended:
        if now.weekday() == 0:
            dirs.append("weekly")
        if now.day == 1:
            dirs.append("monthly")

    return dirs


def run_backup(config: Config, storage: Storage, include_extended: bool) -> None:
    """Run the backup process: create temporary area, collect files, package into archive, and upload to storage."""
    now = datetime.now()
    logger.info("=" * 38)
    logger.info("Starting backup at %s", now.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 38)

    if not config.data_dir.is_dir():
        raise FileNotFoundError(f"Data directory does not exist: {config.data_dir}")

    with tempfile.TemporaryDirectory() as _temp_dir:
        temp_dir = Path(_temp_dir)
        logger.info("Temporary directory: %s", temp_dir)

        archiver = VaultwardenArchiver(config=config, now=now)

        archiver.backup_sqlite(temp_dir)
        archiver.backup_config(temp_dir)
        archiver.backup_rsakey(temp_dir)
        archiver.backup_directory(source=config.resolved_data_attachments, label="attachments", temp_dir=temp_dir)
        archiver.backup_directory(source=config.resolved_data_sends, label="sends", temp_dir=temp_dir)

        archive_path = archiver.package(temp_dir)

        if archive_path:
            sub_dirs = get_retention_sub_dirs(now, include_extended)
            for sub_dir in sub_dirs:
                remote_name = f"{sub_dir}/{archive_path.name}"
                logger.info("Uploading file: %s", remote_name)
                storage.upload(local_path=archive_path, remote_name=remote_name)

            logger.info("Upload completed successfully")

    logger.info("Backup completed successfully at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
