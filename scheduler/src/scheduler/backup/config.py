from pathlib import Path

from mypy_boto3_s3.literals import BucketLocationConstraintType
from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Local filesystem storage
    local_backup_dir: Path = Field(default=Path("./backups"), description="Directory for local filesystem backups")

    # S3 storage
    s3_bucket: str | None = Field(default=None, description="S3 bucket name")
    s3_prefix: str = Field(default="vaultwarden", description="Key prefix inside the S3 bucket")
    s3_region: BucketLocationConstraintType = Field(default="eu-central-1", description="AWS region")
    aws_access_key_id: str | None = Field(default=None, description="AWS access key ID")
    aws_secret_access_key: SecretStr | None = Field(default=None, description="AWS secret access key")

    # Monitoring
    healthchecks_ping_url: HttpUrl | None = Field(
        default=None, description="Healthchecks.io ping URL (e.g. https://hc-ping.com/<uuid>)"
    )

    @field_validator("healthchecks_ping_url", mode="before")
    @classmethod
    def empty_healthchecks_url_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
