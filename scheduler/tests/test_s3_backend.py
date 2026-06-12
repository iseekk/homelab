from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from pytest_mock import MockerFixture

from scheduler.backends.s3 import S3Backend


# --- __init__ ---


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("", ""),
        ("backups", "backups/"),
        ("/backups/", "backups/"),
    ],
)
def test_prefix_normalization(mocker: MockerFixture, prefix: str, expected: str) -> None:
    mocker.patch("scheduler.backends.s3.boto3.client")
    backend = S3Backend(bucket="my-bucket", prefix=prefix)
    assert backend.prefix == expected


def test_boto3_client_called_with_correct_args(mocker: MockerFixture) -> None:
    mock_client = mocker.patch("scheduler.backends.s3.boto3.client")
    S3Backend(bucket="my-bucket", region="us-east-1", access_key_id="KEY", secret_access_key="SECRET")
    mock_client.assert_called_once_with(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="KEY",
        aws_secret_access_key="SECRET",
    )


# --- upload ---


def test_upload_calls_upload_file(mocker: MockerFixture, tmp_path: Path) -> None:
    mock_client = mocker.MagicMock()
    mocker.patch("scheduler.backends.s3.boto3.client", return_value=mock_client)
    f = tmp_path / "backup.7z"
    f.write_bytes(b"data")

    backend = S3Backend(bucket="my-bucket", prefix="")
    backend.upload(f, "backup.7z")

    mock_client.upload_file.assert_called_once_with(str(f), "my-bucket", "backup.7z")


def test_upload_key_with_prefix(mocker: MockerFixture, tmp_path: Path) -> None:
    mock_client = mocker.MagicMock()
    mocker.patch("scheduler.backends.s3.boto3.client", return_value=mock_client)
    f = tmp_path / "backup.7z"
    f.write_bytes(b"data")

    backend = S3Backend(bucket="my-bucket", prefix="backups")
    backend.upload(f, "backup.7z")

    mock_client.upload_file.assert_called_once_with(str(f), "my-bucket", "backups/backup.7z")


def test_upload_propagates_client_error(mocker: MockerFixture, tmp_path: Path) -> None:
    mock_client = mocker.MagicMock()
    mock_client.upload_file.side_effect = ClientError({"Error": {"Code": "NoSuchBucket", "Message": ""}}, "upload_file")
    mocker.patch("scheduler.backends.s3.boto3.client", return_value=mock_client)
    f = tmp_path / "backup.7z"
    f.write_bytes(b"data")

    backend = S3Backend(bucket="missing-bucket")
    with pytest.raises(ClientError, match="NoSuchBucket"):
        backend.upload(f, "backup.7z")
