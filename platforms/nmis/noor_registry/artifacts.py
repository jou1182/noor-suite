"""Content addressed artifact storage for the NMIS demo application.

Artifacts are stored as ``<root>/<first two hex chars>/<sha256 hex digest>``.
The store is deliberately simple: files are immutable, addressed by their
digest, and every lookup is confined to the configured root directory.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import BinaryIO

__all__ = ["ArtifactStore", "StoreError", "confine"]

_ARTIFACT_ID_RE = re.compile(r"[0-9a-f]{64}")
_CHUNK_SIZE = 1024 * 1024


class StoreError(Exception):
    """Raised when an artifact operation cannot be completed safely."""


class ArtifactStore:
    """A small content addressed blob store rooted at ``root``."""

    def __init__(self, root: Path, max_bytes: int = 50 * 1024 * 1024) -> None:
        self.root = Path(root)
        self.max_bytes = int(max_bytes)
        if self.max_bytes <= 0:
            raise StoreError("max_bytes must be a positive number of bytes")

    # ------------------------------------------------------------------
    # writing
    # ------------------------------------------------------------------
    def put_bytes(self, data: bytes) -> str:
        """Store ``data`` and return its sha256 hex digest."""

        if isinstance(data, (bytearray, memoryview)):
            data = bytes(data)
        if not isinstance(data, bytes):
            raise StoreError("data must be bytes")
        if len(data) > self.max_bytes:
            raise StoreError(
                f"artifact of {len(data)} bytes exceeds the limit of {self.max_bytes}"
            )
        digest = hashlib.sha256(data).hexdigest()
        target = self._path_for(digest)
        if target.is_file() and not target.is_symlink():
            return digest
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, data)
        return digest

    def put_file(self, src: Path) -> str:
        """Store the contents of ``src`` and return its sha256 hex digest."""

        source = Path(src)
        if source.is_symlink():
            raise StoreError("source must not be a symlink")
        if not source.exists():
            raise StoreError("source file does not exist")
        if not source.is_file():
            raise StoreError("source must be a regular file")

        self.root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        total = 0
        handle, tmp_name = tempfile.mkstemp(dir=str(self.root), prefix=".tmp-")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(handle, "wb") as out, source.open("rb") as inp:
                while True:
                    chunk = inp.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise StoreError(
                            f"artifact of {total}+ bytes exceeds the limit "
                            f"of {self.max_bytes}"
                        )
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
        except BaseException:
            _unlink_quietly(tmp_path)
            raise

        hexdigest = digest.hexdigest()
        target = self._path_for(hexdigest)
        if target.is_file() and not target.is_symlink():
            _unlink_quietly(tmp_path)
            return hexdigest
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(tmp_path, target)
        except BaseException:
            _unlink_quietly(tmp_path)
            raise
        return hexdigest

    # ------------------------------------------------------------------
    # reading
    # ------------------------------------------------------------------
    def open(self, artifact_id: str) -> BinaryIO:
        """Open a stored artifact for binary reading."""

        path = self._resolve(artifact_id)
        try:
            return path.open("rb")
        except OSError as exc:
            raise StoreError(f"artifact could not be opened: {exc.strerror}") from exc

    def read_bytes(self, artifact_id: str) -> bytes:
        """Return the full contents of a stored artifact."""

        path = self._resolve(artifact_id)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StoreError(f"artifact could not be read: {exc.strerror}") from exc

    def exists(self, artifact_id: str) -> bool:
        """Return ``True`` when a valid id refers to a stored artifact."""

        try:
            self._validate_id(artifact_id)
        except StoreError:
            return False
        target = self._path_for(artifact_id)
        return target.is_file() and not target.is_symlink()

    def size(self, artifact_id: str) -> int:
        """Return the size in bytes of a stored artifact."""

        path = self._resolve(artifact_id)
        try:
            return path.stat().st_size
        except OSError as exc:
            raise StoreError(f"artifact size could not be read: {exc.strerror}") from exc

    def verify(self, artifact_id: str) -> bool:
        """Recompute the digest of a stored artifact and compare it."""

        self._validate_id(artifact_id)
        target = self._path_for(artifact_id)
        if target.is_symlink() or not target.is_file():
            return False
        digest = hashlib.sha256()
        try:
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
                    digest.update(chunk)
        except OSError:
            return False
        return digest.hexdigest() == artifact_id

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _path_for(self, artifact_id: str) -> Path:
        return self.root / artifact_id[:2] / artifact_id

    @staticmethod
    def _validate_id(artifact_id: str) -> str:
        if not isinstance(artifact_id, str):
            raise StoreError("artifact id must be a string")
        if _ARTIFACT_ID_RE.fullmatch(artifact_id) is None:
            raise StoreError("artifact id must be 64 lowercase hex characters")
        return artifact_id

    def _resolve(self, artifact_id: str) -> Path:
        self._validate_id(artifact_id)
        current = self.root
        for part in (artifact_id[:2], artifact_id):
            current = current / part
            if current.is_symlink():
                raise StoreError("artifact path must not contain symlinks")
        try:
            resolved = current.resolve()
        except OSError as exc:  # pragma: no cover - defensive
            raise StoreError("artifact path could not be resolved") from exc
        if not resolved.is_relative_to(self.root.resolve()):
            raise StoreError("artifact path escapes the store root")
        if not resolved.is_file():
            raise StoreError("artifact not found")
        return resolved

    def _atomic_write(self, target: Path, data: bytes) -> None:
        handle, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp-")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp_path, target)
        except BaseException:
            _unlink_quietly(tmp_path)
            raise


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def confine(root: Path, name: str) -> Path:
    """Resolve ``name`` as a plain file name inside ``root``.

    ``name`` is treated as a single file name chosen by a user: absolute
    paths, drive letters, path separators, ``..`` segments, NUL bytes and
    dot-prefixed names are rejected.  The candidate must exist, must be a
    regular file, must not be a symlink and must resolve inside ``root``.
    """

    root_path = Path(root)
    if not isinstance(name, str) or not name.strip():
        raise StoreError("name must be a non-empty string")
    if "\x00" in name:
        raise StoreError("name must not contain a NUL character")
    if os.path.isabs(name) or name.startswith("/") or name.startswith("\\"):
        raise StoreError("name must be a plain file name, not an absolute path")
    if len(name) >= 2 and name[1] == ":":
        raise StoreError("name must not contain a drive letter")
    if "/" in name or "\\" in name:
        raise StoreError("name must not contain a path separator")
    if ".." in name:
        raise StoreError("name must not contain '..'")
    if name.startswith("."):
        raise StoreError("name must not start with '.'")

    candidate = root_path / name
    if candidate.is_symlink():
        raise StoreError("name must not refer to a symlink")
    if not candidate.exists():
        raise StoreError("no such file")
    if not candidate.is_file():
        raise StoreError("name must refer to a regular file")

    resolved = candidate.resolve()
    if not resolved.is_relative_to(root_path.resolve()):
        raise StoreError("name escapes the root directory")
    return resolved
