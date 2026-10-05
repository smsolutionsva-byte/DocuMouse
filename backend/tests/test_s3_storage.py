from io import BytesIO
from unittest.mock import MagicMock, patch
import botocore.exceptions
import pytest

from documouse.config import Settings
from documouse.storage import get_storage
from documouse.storage.local import LocalStorage
from documouse.storage.s3 import S3Storage


def test_s3_storage_operations():
    with patch("boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3

        storage = S3Storage(
            bucket="test-bucket",
            endpoint_url="https://r2.example.com",
            region="auto",
            access_key_id="test-key",
            secret_access_key="test-secret",
        )

        mock_boto.assert_called_once_with(
            "s3",
            endpoint_url="https://r2.example.com",
            region_name="auto",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
        )

        # put
        storage.put("docs/1/file.pdf", b"pdf-data")
        mock_s3.put_object.assert_called_once_with(
            Bucket="test-bucket", Key="docs/1/file.pdf", Body=b"pdf-data"
        )

        # get
        mock_s3.get_object.return_value = {"Body": BytesIO(b"returned-bytes")}
        assert storage.get("docs/1/file.pdf") == b"returned-bytes"
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="docs/1/file.pdf"
        )

        # exists True
        mock_s3.head_object.return_value = {}
        assert storage.exists("docs/1/file.pdf") is True

        # exists False on 404
        mock_s3.head_object.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )
        assert storage.exists("docs/1/missing.pdf") is False

        # exists raises on other errors
        mock_s3.head_object.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject"
        )
        with pytest.raises(botocore.exceptions.ClientError):
            storage.exists("docs/1/forbidden.pdf")

        # delete_prefix
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "docs/1/a"}, {"Key": "docs/1/b"}]}
        ]
        storage.delete_prefix("docs/1/")
        mock_s3.delete_objects.assert_called_once_with(
            Bucket="test-bucket",
            Delete={"Objects": [{"Key": "docs/1/a"}, {"Key": "docs/1/b"}], "Quiet": True},
        )


def test_get_storage_factory():
    get_storage.cache_clear()
    with patch("documouse.storage.get_settings") as mock_settings:
        mock_settings.return_value = Settings(storage_backend="local")
        store = get_storage()
        assert isinstance(store, LocalStorage)

    get_storage.cache_clear()
    with patch("documouse.storage.get_settings") as mock_settings, patch("boto3.client"):
        mock_settings.return_value = Settings(
            storage_backend="s3",
            s3_bucket="my-bucket",
            s3_access_key_id="k",
            s3_secret_access_key="s",
        )
        store = get_storage()
        assert isinstance(store, S3Storage)
        assert store.bucket == "my-bucket"
    get_storage.cache_clear()
