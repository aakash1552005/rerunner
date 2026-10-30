"""Unit tests for pluggable cassette storage backends (Local, S3, GCS)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from rerunner.storage import (
    GCSStorageBackend,
    LocalStorageBackend,
    S3StorageBackend,
    StorageBackendError,
    get_storage_backend,
)


def test_get_storage_backend_resolution() -> None:
    assert isinstance(get_storage_backend("tests/cassettes/test.jsonl"), LocalStorageBackend)
    assert isinstance(get_storage_backend("file:///tmp/cassette.jsonl"), LocalStorageBackend)
    assert isinstance(get_storage_backend("s3://my-bucket/test.jsonl"), S3StorageBackend)
    assert isinstance(get_storage_backend("gs://my-bucket/test.jsonl"), GCSStorageBackend)


def test_local_storage_backend_read_write(tmp_path: Path) -> None:
    backend = LocalStorageBackend()
    test_file = tmp_path / "test_storage.jsonl"
    data = b'{"test": true}\n'

    assert not backend.exists(str(test_file))
    backend.write_bytes(str(test_file), data)
    assert backend.exists(str(test_file))

    read_data = backend.read_bytes(str(test_file))
    assert read_data == data

    backend.delete(str(test_file))
    assert not backend.exists(str(test_file))


def test_s3_storage_backend_mocked() -> None:
    mock_s3 = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = b'{"format_version": "0.1"}\n'
    mock_s3.get_object.return_value = {"Body": mock_body}

    backend = S3StorageBackend(s3_client=mock_s3)
    uri = "s3://ci-cassettes/agent-run-1.jsonl"

    # Test read
    data = backend.read_bytes(uri)
    assert data == b'{"format_version": "0.1"}\n'
    mock_s3.get_object.assert_called_once_with(Bucket="ci-cassettes", Key="agent-run-1.jsonl")

    # Test write
    backend.write_bytes(uri, b"new_bytes")
    mock_s3.put_object.assert_called_once_with(
        Bucket="ci-cassettes", Key="agent-run-1.jsonl", Body=b"new_bytes"
    )

    # Test exists
    assert backend.exists(uri) is True
    mock_s3.head_object.assert_called_once_with(Bucket="ci-cassettes", Key="agent-run-1.jsonl")

    # Test delete
    backend.delete(uri)
    mock_s3.delete_object.assert_called_once_with(Bucket="ci-cassettes", Key="agent-run-1.jsonl")


def test_s3_storage_backend_invalid_uri() -> None:
    backend = S3StorageBackend(s3_client=MagicMock())
    with pytest.raises(StorageBackendError, match="Invalid S3 URI format"):
        backend.read_bytes("http://example.com/cassette.jsonl")


def test_gcs_storage_backend_mocked() -> None:
    mock_gcs = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = b'{"format_version": "0.1"}\n'
    mock_blob.exists.return_value = True
    mock_bucket.blob.return_value = mock_blob
    mock_gcs.bucket.return_value = mock_bucket

    backend = GCSStorageBackend(gcs_client=mock_gcs)
    uri = "gs://team-storage/traces/cassette.jsonl"

    # Test read
    data = backend.read_bytes(uri)
    assert data == b'{"format_version": "0.1"}\n'
    mock_gcs.bucket.assert_called_once_with("team-storage")
    mock_bucket.blob.assert_called_once_with("traces/cassette.jsonl")

    # Test write
    backend.write_bytes(uri, b"gcs_payload")
    mock_blob.upload_from_string.assert_called_once_with(b"gcs_payload")

    # Test exists
    assert backend.exists(uri) is True

    # Test delete
    backend.delete(uri)
    mock_blob.delete.assert_called_once()


def test_azure_blob_storage_backend_mocked() -> None:
    from rerunner.storage import AzureBlobStorageBackend, get_storage_backend

    mock_blob_service = MagicMock()
    mock_container = MagicMock()
    mock_blob = MagicMock()
    mock_download = MagicMock()
    mock_download.readall.return_value = b'{"format_version": "0.1"}\n'
    mock_blob.download_blob.return_value = mock_download
    mock_blob.exists.return_value = True
    mock_container.get_blob_client.return_value = mock_blob
    mock_blob_service.get_container_client.return_value = mock_container

    backend = AzureBlobStorageBackend(blob_service_client=mock_blob_service)
    uri = "az://cassettes/agent_run.jsonl"

    # Test read
    data = backend.read_bytes(uri)
    assert data == b'{"format_version": "0.1"}\n'
    mock_blob_service.get_container_client.assert_called_once_with("cassettes")
    mock_container.get_blob_client.assert_called_once_with("agent_run.jsonl")

    # Test write
    backend.write_bytes(uri, b"azure_payload")
    mock_blob.upload_blob.assert_called_once_with(b"azure_payload", overwrite=True)

    # Test exists
    assert backend.exists(uri) is True

    # Test delete
    backend.delete(uri)
    mock_blob.delete_blob.assert_called_once()

    # Test get_storage_backend resolution
    assert isinstance(get_storage_backend("az://mycontainer/path.jsonl"), AzureBlobStorageBackend)
    assert isinstance(
        get_storage_backend("azure://mycontainer/path.jsonl"), AzureBlobStorageBackend
    )
