import logging
import time

import schedule

from scheduler.backends.monitoring.base import Monitor
from scheduler.backends.monitoring.healthchecks import HealthchecksMonitor
from scheduler.backends.monitoring.noop import NoopMonitor
from scheduler.backends.storage.base import Storage
from scheduler.backends.storage.local import LocalFilesystemStorage
from scheduler.backends.storage.s3 import S3Storage
from scheduler.backup.archiver import run_backup
from scheduler.config import Config

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure logging to output to the console with a consistent format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def create_storage(config: Config) -> Storage:
    """Create a storage from configuration."""
    if config.s3_bucket:
        if not config.aws_access_key_id or not config.aws_secret_access_key:
            raise ValueError("AWS credentials must be provided when using S3 storage")
        logger.info("Storage: AWS S3 (s3://%s/%s)", config.s3_bucket, config.s3_prefix)
        return S3Storage(
            bucket=config.s3_bucket,
            prefix=config.s3_prefix,
            region=config.s3_region,
            access_key_id=config.aws_access_key_id,
            secret_access_key=config.aws_secret_access_key.get_secret_value(),
        )

    logger.info("Storage: Local filesystem (%s)", config.local_backup_dir)
    return LocalFilesystemStorage(
        remote_dir=config.local_backup_dir,
        retention_days={
            "daily": config.retention_daily_days,
            "weekly": config.retention_weekly_days,
            "monthly": config.retention_monthly_days,
        },
    )


def create_monitor(config: Config) -> Monitor:
    """Create a monitor from configuration."""
    if config.healthchecks_ping_url:
        return HealthchecksMonitor(str(config.healthchecks_ping_url))
    return NoopMonitor()


def schedule_backup_jobs() -> None:
    """Set up the backup jobs according to the configuration."""
    logger.info("Scheduling backup jobs...")
    config = Config()  # type: ignore[call-arg]  # required fields are read from the environment
    storage = create_storage(config)
    monitor = create_monitor(config)

    def _job(is_first_run_of_day: bool) -> None:
        monitor.start()
        try:
            run_backup(config, storage, is_first_run_of_day)
        except Exception:
            monitor.fail()
            logger.exception("Backup job failed")
        else:
            monitor.success()

    for i, run_time in enumerate(sorted(config.resolved_backup_times)):
        is_first_run_of_day = i == 0
        schedule.every().day.at(run_time).do(_job, is_first_run_of_day=is_first_run_of_day)
        logger.info("Scheduled backup at: %s (first run of the day: %s)", run_time, is_first_run_of_day)


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
