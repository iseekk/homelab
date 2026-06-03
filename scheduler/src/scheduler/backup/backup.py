import logging
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

import py7zr
from mypy_boto3_s3.literals import BucketLocationConstraintType
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from scheduler.backends.base import StorageBackend

logger = logging.getLogger(__name__)


class BackupConfig(BaseSettings):
    """Configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Vaultwarden data paths
    data_dir: Path = Field(default=Path("/data"), description="Vaultwarden data directory")
    data_db: Path | None = Field(
        default=None, description="Path to the SQLite database file (default: data_dir/db.sqlite3)"
    )
    data_rsakey: Path | None = Field(default=None, description="RSA key files prefix (default: data_dir/rsa_key)")
    data_attachments: Path | None = Field(
        default=None, description="Attachments directory (default: data_dir/attachments)"
    )
    data_sends: Path | None = Field(default=None, description="Sends directory (default: data_dir/sends)")

    # File name format
    backup_file_date_format: str = Field(default="%Y-%m-%d-%H%M", description="Date format used in backup file names")

    # Compression
    archive_password: SecretStr | None = Field(default=None, description="Password for the archive")

    # Schedule
    backup_times: str = Field(
        default="02:00, 06:00, 10:00, 14:00, 18:00, 22:00",
        description="Comma-separated list of times (HH:MM) to run the backup",
    )

    # Local filesystem backend
    local_backup_dir: Path = Field(default=Path("./backups"), description="Directory for local filesystem backups")

    # S3 backend
    s3_bucket: str | None = Field(default=None, description="S3 bucket name")
    s3_prefix: str = Field(default="vaultwarden", description="Key prefix inside the S3 bucket")
    s3_region: BucketLocationConstraintType = Field(default="eu-central-1", description="AWS region")
    aws_access_key_id: str | None = Field(default=None, description="AWS access key ID")
    aws_secret_access_key: SecretStr | None = Field(default=None, description="AWS secret access key")

    @property
    def resolved_data_db(self) -> Path:
        return self.data_db or self.data_dir / "db.sqlite3"

    @property
    def resolved_data_config(self) -> Path:
        return self.data_dir / "config.json"

    @property
    def resolved_data_rsakey(self) -> Path:
        return self.data_rsakey or self.data_dir / "rsa_key"

    @property
    def resolved_data_attachments(self) -> Path:
        return self.data_attachments or self.data_dir / "attachments"

    @property
    def resolved_data_sends(self) -> Path:
        return self.data_sends or self.data_dir / "sends"

    @property
    def resolved_backup_times(self) -> list[str]:
        return [t.strip() for t in self.backup_times.split(",") if t.strip()]


class VaultwardenArchiver:
    """Responsible for collecting Vaultwarden files and packaging them into a password-protected archive."""

    def __init__(self, config: BackupConfig, now: datetime) -> None:
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
        with closing(sqlite3.connect(db_path)) as src_conn, closing(sqlite3.connect(dest)) as dst_conn:
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
        if not any(temp_dir.iterdir()):
            logger.warning("No files to archive in temporary directory: %s — skipping archive creation", temp_dir)
            return None

        archive_path = temp_dir.parent / f"backup.{self.now_str}.7z"

        password = self.config.archive_password.get_secret_value() if self.config.archive_password else None
        if not password:
            logger.warning("No archive password provided — creating unencrypted archive (not recommended)")
        with py7zr.SevenZipFile(
            file=archive_path,
            mode="w",
            password=password,
            header_encryption=True,
        ) as archive:
            for file in sorted(temp_dir.iterdir()):
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


def run_backup(config: BackupConfig, backend: StorageBackend, include_extended: bool) -> None:
    """Run the backup process: create temporary area, collect files, package into archive, and upload to backend."""
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
                backend.upload(local_path=archive_path, remote_name=remote_name)

            logger.info("Upload completed successfully")

    logger.info("Backup completed successfully at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
