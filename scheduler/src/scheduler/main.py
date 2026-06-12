import logging
import time

import schedule

from scheduler.backends.base import StorageBackend
from scheduler.backends.local import LocalFilesystemBackend
from scheduler.backends.s3 import S3Backend
from scheduler.backup.backup import BackupConfig, run_backup

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure logging to output to the console with a consistent format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def schedule_backup_jobs() -> None:
    """Set up the backup jobs according to the configuration."""
    logger.info("Scheduling backup jobs...")
    config = BackupConfig()
    backend: StorageBackend
    if config.s3_bucket:
        if not config.aws_access_key_id or not config.aws_secret_access_key:
            raise ValueError("AWS credentials must be provided when using S3 backend")
        backend = S3Backend(
            bucket=config.s3_bucket,
            prefix=config.s3_prefix,
            region=config.s3_region,
            access_key_id=config.aws_access_key_id,
            secret_access_key=config.aws_secret_access_key.get_secret_value(),
        )
        logger.info("Backend: AWS S3 (s3://%s/%s)", config.s3_bucket, config.s3_prefix)
    else:
        backend = LocalFilesystemBackend(remote_dir=config.local_backup_dir)
        logger.info("Backend: Local filesystem (%s)", config.local_backup_dir)

    def _job(include_extended: bool) -> None:
        try:
            run_backup(config, backend, include_extended)
        except Exception:
            logger.exception("Backup job failed")

    for i, run_time in enumerate(sorted(config.resolved_backup_times)):
        is_first_run = i == 0
        schedule.every().day.at(run_time).do(_job, include_extended=is_first_run)
        logger.info("Scheduled backup at: %s (extended retention: %s)", run_time, is_first_run)


def main() -> None:
    """Set up logging, schedule jobs, and run the scheduler loop."""
    setup_logging()
    schedule_backup_jobs()

    while True:
        n = schedule.idle_seconds()
        if n is None:
            logger.warning("No more jobs scheduled, exiting.")
            break
        elif n > 0:
            time.sleep(max(n, 1.0))
        schedule.run_pending()


if __name__ == "__main__":
    main()
