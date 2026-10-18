# RFC 0001: Pluggable Cloud Remote Storage Drivers (S3, GCS, Azure)

* **RFC PR:** #10
* **Target Release:** v0.2.1
* **Author(s):** Rerunner Core Architecture Working Group
* **Status:** 🟡 Approved
* **Created:** 2026-10-13

---

## 1. Summary

This RFC defines a modular storage driver subsystem (`rerunner.storage`) that decouples Rerunner from local disk persistence. It introduces a `BaseStorageDriver` protocol and native drivers for **AWS S3** (`s3://`), **Google Cloud Storage** (`gs://`), and **Azure Blob Storage** (`az://`), enabling enterprise CI/CD runners to fetch and upload `.jsonl.gz` cassettes directly from central object stores.

---

## 2. Motivation & Enterprise Problem Statement

Enterprise engineering teams running thousands of PRs daily face two major limitations with local file cassettes:
1. **Ephemeral CI Runners:** In environments like AWS CodeBuild, Kubernetes pods, or GitHub Actions matrix builds, local cassettes cannot easily be shared or updated without complex git commits.
2. **Centralized Replay Cache:** Teams want a single company-wide S3 or GCS bucket where previously recorded agent runs are cached and deduplicated by hash, eliminating redundant model calls across different developer laptops and CI machines.

---

## 3. Detailed Technical Specification

### 3.1 Public API & URI Scheme

Rerunner will automatically resolve storage drivers based on URI scheme:

```python
from rerunner import CassetteTransport

# Automatically connects to AWS S3 driver via s3:// URI
transport = CassetteTransport("s3://ai-team-traces/evals/agent_run.jsonl.gz", mode="replay")

# Programmatic storage configuration
from rerunner.storage import S3StorageDriver, register_storage_driver

driver = S3StorageDriver(bucket="ai-team-traces", region="us-east-1")
register_storage_driver("s3", driver)
```

### 3.2 Storage Driver Interface

All storage backends must implement the `BaseStorageDriver` protocol:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseStorageDriver(Protocol):
    """Protocol for pluggable cassette persistence drivers."""

    def read_bytes(self, uri: str) -> bytes:
        """Download and return raw cassette bytes from remote storage."""
        ...

    def write_bytes(self, uri: str, data: bytes) -> None:
        """Upload raw cassette bytes to remote storage."""
        ...

    def exists(self, uri: str) -> bool:
        """Check if a cassette exists at the given URI."""
        ...
```

### 3.3 Packaging & Optional Dependencies

To avoid bloating the core runtime, cloud SDKs are packaged as extras in `pyproject.toml`:
```toml
[project.optional-dependencies]
s3 = ["boto3>=1.34.0"]
gcs = ["google-cloud-storage>=2.14.0"]
all-storage = ["rerunner[s3,gcs]"]
```

---

## 4. Drawbacks & Alternatives Considered

* **Alternative 1 (Git LFS):** Storing large cassettes in Git LFS causes repository bloat and slows down clone times. S3/GCS directly solves this.
* **Alternative 2 (Local file syncing scripts):** Requires custom shell scripts around test execution. Native URI support provides zero-friction developer experience.

---

## 5. Implementation Roadmap

- [ ] Define `BaseStorageDriver` protocol in `src/rerunner/storage/base.py`
- [ ] Implement `LocalStorageDriver` as default fallback
- [ ] Implement `S3StorageDriver` using `boto3`
- [ ] Implement `GCSStorageDriver` using `google-cloud-storage`
- [ ] Add URI dispatching logic in `Cassette.load()` and `Cassette.save()`
- [ ] Add unit tests using `moto` mocks
