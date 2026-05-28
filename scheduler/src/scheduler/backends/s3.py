import logging
from pathlib import Path

import boto3
from mypy_boto3_s3 import S3Client

from scheduler.backends.base import StorageBackend

logger = logging.getLogger(__name__)


class S3Backend(StorageBackend):
    """Amazon S3 storage backend."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = "eu-central-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self.bucket = bucket
        # Normalize prefix: no leading slash, trailing slash only if non-empty
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self.client: S3Client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def upload(self, local_path: Path, remote_name: str) -> None:
        key = f"{self.prefix}{remote_name}"
        file_size = local_path.stat().st_size
        logger.info("Uploading '%s' → s3://%s/%s (%d bytes)", local_path.name, self.bucket, key, file_size)
        self.client.upload_file(str(local_path), self.bucket, key)
        logger.info("Upload completed")
