"""Remote storage backend interface and implementations for Rerunner cassettes.

Supports local filesystem, AWS S3 (`s3://`), and Google Cloud Storage (`gs://`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import contextlib
import hashlib
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse
import uuid

if TYPE_CHECKING:
    pass

SUPPORTED_EXTENSIONS = (
    ".cassette.zst",
    ".zst",
    ".jsonl.gz",
    ".gz",
    ".jsonl",
    ".json",
)


def detect_compression(uri: str) -> Literal["zstd", "gzip", "none"]:
    """Detect compression format from URI or file path."""
    lower = uri.lower()
    if lower.endswith(".cassette.zst") or lower.endswith(".zst"):
        return "zstd"
    if lower.endswith(".jsonl.gz") or lower.endswith(".gz"):
        return "gzip"
    return "none"


def is_supported_cassette_extension(uri: str) -> bool:
    """Return whether the URI has a supported cassette file extension."""
    lower = uri.lower()
    return any(lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS)


class StorageBackendError(Exception):
    """Raised when remote or local storage backend operations fail."""


class BaseStorageBackend(ABC):
    """Abstract base class for cassette storage backends."""

    @abstractmethod
    def read_bytes(self, uri: str) -> bytes:
        """Read raw bytes of a cassette from the specified URI."""

    @abstractmethod
    def write_bytes(self, uri: str, data: bytes) -> None:
        """Write raw bytes of a cassette to the specified URI."""

    @abstractmethod
    def exists(self, uri: str) -> bool:
        """Check whether a cassette exists at the specified URI."""

    @abstractmethod
    def delete(self, uri: str) -> None:
        """Delete a cassette at the specified URI."""


class LocalStorageBackend(BaseStorageBackend):
    """Local filesystem storage backend."""

    def _to_path(self, uri: str) -> Path:
        if uri.startswith("file://"):
            parsed = urlparse(uri)
            # Support both windows and unix path parsing from file URI
            path_str = parsed.path
            if re.match(r"^/[a-zA-Z]:", path_str):
                path_str = path_str[1:]
            return Path(path_str)
        return Path(uri)

    def read_bytes(self, uri: str) -> bytes:
        path = self._to_path(uri)
        if not path.exists():
            raise FileNotFoundError(f"Local cassette file not found: {path}")
        return path.read_bytes()

    def write_bytes(self, uri: str, data: bytes) -> None:
        path = self._to_path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        unique_suffix = f"{path.suffix}.{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
        temp_path = path.with_suffix(unique_suffix)
        try:
            temp_path.write_bytes(data)
            temp_path.replace(path)
        except BaseException:
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()
            raise

    def exists(self, uri: str) -> bool:
        return self._to_path(uri).exists()

    def delete(self, uri: str) -> None:
        path = self._to_path(uri)
        if path.exists():
            path.unlink()


class S3StorageBackend(BaseStorageBackend):
    """AWS S3 cassette storage backend (requires boto3)."""

    def __init__(self, s3_client: object | None = None) -> None:
        self._client = s3_client

    def _get_client(self) -> object:
        if self._client is None:
            try:
                import boto3  # type: ignore[import-untyped]

                self._client = boto3.client("s3")
            except ImportError as err:
                raise StorageBackendError(
                    "boto3 is required for S3 remote cassette storage. "
                    "Install it via `pip install rerunner[s3]` or `pip install boto3`."
                ) from err
        return self._client

    def _parse_s3_uri(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise StorageBackendError(f"Invalid S3 URI format: '{uri}'. Expected 's3://bucket/key'")
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        return bucket, key

    def read_bytes(self, uri: str) -> bytes:
        bucket, key = self._parse_s3_uri(uri)
        client: Any = self._get_client()
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()  # type: ignore[no-any-return]
        except Exception as exc:
            raise StorageBackendError(
                f"Failed to read cassette from S3 URI '{uri}': {exc}"
            ) from exc

    def write_bytes(self, uri: str, data: bytes) -> None:
        bucket, key = self._parse_s3_uri(uri)
        client: Any = self._get_client()
        try:
            client.put_object(Bucket=bucket, Key=key, Body=data)
        except Exception as exc:
            raise StorageBackendError(f"Failed to write cassette to S3 URI '{uri}': {exc}") from exc

    def exists(self, uri: str) -> bool:
        bucket, key = self._parse_s3_uri(uri)
        client: Any = self._get_client()
        try:
            client.head_object(Bucket=bucket, Key=key)
            return True
        except Exception as exc:
            error_code = ""
            if hasattr(exc, "response") and isinstance(exc.response, dict):
                error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            err_str = str(exc).lower()
            if "404" in err_str or "not found" in err_str or "nosuchkey" in err_str:
                return False
            raise StorageBackendError(
                f"Error checking existence of S3 cassette '{uri}': {exc}"
            ) from exc

    def delete(self, uri: str) -> None:
        bucket, key = self._parse_s3_uri(uri)
        client: Any = self._get_client()
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            raise StorageBackendError(
                f"Failed to delete cassette at S3 URI '{uri}': {exc}"
            ) from exc


class GCSStorageBackend(BaseStorageBackend):
    """Google Cloud Storage (GCS) cassette storage backend (requires google-cloud-storage)."""

    def __init__(self, gcs_client: object | None = None) -> None:
        self._client = gcs_client

    def _get_client(self) -> object:
        if self._client is None:
            try:
                from google.cloud import storage  # type: ignore[import-untyped]

                self._client = storage.Client()
            except ImportError as err:
                raise StorageBackendError(
                    "google-cloud-storage is required for GCS remote cassette storage. "
                    "Install it via `pip install rerunner[gcs]` or `pip install google-cloud-storage`."
                ) from err
        return self._client

    def _parse_gcs_uri(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "gs" or not parsed.netloc:
            raise StorageBackendError(
                f"Invalid GCS URI format: '{uri}'. Expected 'gs://bucket/blob_name'"
            )
        bucket = parsed.netloc
        blob_name = parsed.path.lstrip("/")
        return bucket, blob_name

    def read_bytes(self, uri: str) -> bytes:
        bucket_name, blob_name = self._parse_gcs_uri(uri)
        client: Any = self._get_client()
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            return blob.download_as_bytes()  # type: ignore[no-any-return]
        except Exception as exc:
            raise StorageBackendError(
                f"Failed to read cassette from GCS URI '{uri}': {exc}"
            ) from exc

    def write_bytes(self, uri: str, data: bytes) -> None:
        bucket_name, blob_name = self._parse_gcs_uri(uri)
        client: Any = self._get_client()
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.upload_from_string(data)
        except Exception as exc:
            raise StorageBackendError(
                f"Failed to write cassette to GCS URI '{uri}': {exc}"
            ) from exc

    def exists(self, uri: str) -> bool:
        bucket_name, blob_name = self._parse_gcs_uri(uri)
        client: Any = self._get_client()
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            return blob.exists()  # type: ignore[no-any-return]
        except Exception as exc:
            err_str = str(exc).lower()
            if "404" in err_str or "not found" in err_str:
                return False
            raise StorageBackendError(
                f"Error checking existence of GCS cassette '{uri}': {exc}"
            ) from exc

    def delete(self, uri: str) -> None:
        bucket_name, blob_name = self._parse_gcs_uri(uri)
        client: Any = self._get_client()
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.delete()
        except Exception as exc:
            raise StorageBackendError(
                f"Failed to delete cassette at GCS URI '{uri}': {exc}"
            ) from exc


class AzureBlobStorageBackend(BaseStorageBackend):
    """Microsoft Azure Blob Storage cassette backend (requires azure-storage-blob)."""

    def __init__(self, blob_service_client: object | None = None) -> None:
        self._client = blob_service_client

    def _get_client(self) -> object:
        if self._client is None:
            try:
                from azure.storage.blob import BlobServiceClient  # type: ignore[import-untyped]

                connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
                account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")
                if connection_string:
                    self._client = BlobServiceClient.from_connection_string(connection_string)
                elif account_url:
                    self._client = BlobServiceClient(account_url=account_url)
                else:
                    raise StorageBackendError(
                        "Azure Blob Storage requires AZURE_STORAGE_CONNECTION_STRING or "
                        "AZURE_STORAGE_ACCOUNT_URL environment variable to be set."
                    )
            except ImportError as err:
                raise StorageBackendError(
                    "azure-storage-blob is required for Azure remote cassette storage. "
                    "Install it via `pip install rerunner[azure]` or `pip install azure-storage-blob`."
                ) from err
        return self._client

    def _parse_azure_uri(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme not in ("az", "azure") or not parsed.netloc:
            raise StorageBackendError(
                f"Invalid Azure Blob URI format: '{uri}'. Expected 'az://container/blob_name' or 'azure://container/blob_name'"
            )
        container = parsed.netloc
        blob_name = parsed.path.lstrip("/")
        return container, blob_name

    def read_bytes(self, uri: str) -> bytes:
        container_name, blob_name = self._parse_azure_uri(uri)
        client: Any = self._get_client()
        try:
            container_client = client.get_container_client(container_name)
            blob_client = container_client.get_blob_client(blob_name)
            return blob_client.download_blob().readall()  # type: ignore[no-any-return]
        except Exception as exc:
            raise StorageBackendError(
                f"Failed to read cassette from Azure URI '{uri}': {exc}"
            ) from exc

    def write_bytes(self, uri: str, data: bytes) -> None:
        container_name, blob_name = self._parse_azure_uri(uri)
        client: Any = self._get_client()
        try:
            container_client = client.get_container_client(container_name)
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.upload_blob(data, overwrite=True)
        except Exception as exc:
            raise StorageBackendError(
                f"Failed to write cassette to Azure URI '{uri}': {exc}"
            ) from exc

    def exists(self, uri: str) -> bool:
        container_name, blob_name = self._parse_azure_uri(uri)
        client: Any = self._get_client()
        try:
            container_client = client.get_container_client(container_name)
            blob_client = container_client.get_blob_client(blob_name)
            return blob_client.exists()  # type: ignore[no-any-return]
        except Exception as exc:
            err_str = str(exc).lower()
            if "404" in err_str or "not found" in err_str or "blobnotfound" in err_str:
                return False
            raise StorageBackendError(
                f"Error checking existence of Azure cassette '{uri}': {exc}"
            ) from exc

    def delete(self, uri: str) -> None:
        container_name, blob_name = self._parse_azure_uri(uri)
        client: Any = self._get_client()
        try:
            container_client = client.get_container_client(container_name)
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
        except Exception as exc:
            raise StorageBackendError(
                f"Failed to delete cassette at Azure URI '{uri}': {exc}"
            ) from exc


class CachedRemoteBackend(BaseStorageBackend):
    """Local disk-cached wrapper around a remote BaseStorageBackend (Issue #83).

    Avoids re-downloading large compressed cassettes across parallel CI workers
    by caching payloads under ``~/.cache/rerunner/cassettes`` (or ``RERUNNER_CACHE_DIR``).
    """

    def __init__(
        self,
        remote: BaseStorageBackend,
        cache_dir: Path | None = None,
    ) -> None:
        self.remote = remote
        env_dir = os.getenv("RERUNNER_CACHE_DIR")
        self.cache_dir = (
            cache_dir
            if cache_dir is not None
            else (Path(env_dir) if env_dir else Path.home() / ".cache" / "rerunner" / "cassettes")
        )

    def _cache_path(self, uri: str) -> Path:
        digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.bin"

    def invalidate(self, uri: str) -> None:
        """Remove a cached URI entry from disk if present."""
        cache_file = self._cache_path(uri)
        with contextlib.suppress(OSError):
            if cache_file.exists():
                cache_file.unlink()

    def read_bytes(self, uri: str) -> bytes:
        cache_file = self._cache_path(uri)
        if cache_file.exists():
            return cache_file.read_bytes()
        data = self.remote.read_bytes(uri)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_dir / f".{cache_file.stem}.{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
        try:
            tmp.write_bytes(data)
            tmp.replace(cache_file)
        finally:
            if tmp.exists():
                with contextlib.suppress(OSError):
                    tmp.unlink()
        return data

    def write_bytes(self, uri: str, data: bytes) -> None:
        self.remote.write_bytes(uri, data)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._cache_path(uri)
        tmp = self.cache_dir / f".{cache_file.stem}.{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
        try:
            tmp.write_bytes(data)
            tmp.replace(cache_file)
        finally:
            if tmp.exists():
                with contextlib.suppress(OSError):
                    tmp.unlink()

    def exists(self, uri: str) -> bool:
        if self._cache_path(uri).exists():
            return True
        return self.remote.exists(uri)

    def delete(self, uri: str) -> None:
        self.invalidate(uri)
        self.remote.delete(uri)


def get_storage_backend(uri: str, *, use_cache: bool | None = None) -> BaseStorageBackend:
    """Resolve the appropriate storage backend based on URI scheme."""
    cache_enabled = (
        use_cache
        if use_cache is not None
        else os.getenv("RERUNNER_REMOTE_CACHE", "").strip().lower() in {"1", "true", "yes"}
    )
    if uri.startswith("s3://"):
        backend: BaseStorageBackend = S3StorageBackend()
        return CachedRemoteBackend(backend) if cache_enabled else backend
    if uri.startswith("gs://"):
        backend = GCSStorageBackend()
        return CachedRemoteBackend(backend) if cache_enabled else backend
    if uri.startswith("az://") or uri.startswith("azure://"):
        backend = AzureBlobStorageBackend()
        return CachedRemoteBackend(backend) if cache_enabled else backend
    return LocalStorageBackend()


REMOTE_URI_PREFIXES = ("s3://", "gs://", "az://", "azure://")


def is_remote_uri(uri: Path | str) -> bool:
    """Return True when the cassette reference points to a cloud object store URI."""
    return str(uri).startswith(REMOTE_URI_PREFIXES)


def resolve_cassette_ref(cassette_path: Path | str) -> tuple[Path | str, str]:
    """Normalize a cassette reference without coercing remote URIs into Path objects."""
    uri = str(cassette_path)
    if is_remote_uri(uri):
        return uri, uri
    return Path(cassette_path), uri


def cassette_exists(cassette_path: Path | str) -> bool:
    """Check whether a local or remote cassette exists via its storage backend."""
    uri = str(cassette_path)
    return get_storage_backend(uri).exists(uri)
