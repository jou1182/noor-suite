"""Tests for :mod:`noor_registry.artifacts` (T024/T025)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from noor_registry.artifacts import ArtifactStore, StoreError, confine


@pytest.fixture()
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts")


def test_put_bytes_round_trip(store: ArtifactStore) -> None:
    payload = b"hello noor registry"
    artifact_id = store.put_bytes(payload)
    assert len(artifact_id) == 64
    assert artifact_id == hashlib.sha256(payload).hexdigest()
    assert store.read_bytes(artifact_id) == payload
    with store.open(artifact_id) as handle:
        assert handle.read() == payload


def test_put_bytes_is_idempotent(store: ArtifactStore) -> None:
    first = store.put_bytes(b"same")
    second = store.put_bytes(b"same")
    assert first == second
    shard = store.root / first[:2]
    assert [p.name for p in shard.iterdir()] == [first]


def test_different_content_yields_different_ids(store: ArtifactStore) -> None:
    assert store.put_bytes(b"one") != store.put_bytes(b"two")


def test_stored_layout_is_sharded(store: ArtifactStore) -> None:
    artifact_id = store.put_bytes(b"layout")
    assert artifact_id.islower()
    assert artifact_id == artifact_id.lower()
    target = store.root / artifact_id[:2] / artifact_id
    assert target.is_file()
    assert target.read_bytes() == b"layout"
    assert target.suffix == ""


def test_put_file_round_trip(store: ArtifactStore, tmp_path: Path) -> None:
    source = tmp_path / "upload.bin"
    source.write_bytes(b"file payload")
    artifact_id = store.put_file(source)
    assert artifact_id == hashlib.sha256(b"file payload").hexdigest()
    assert store.read_bytes(artifact_id) == b"file payload"


@pytest.mark.parametrize(
    "bad_id",
    ["..", "abc", "A" * 64, "a" * 63, "a" * 65, "", "g" * 64, "a" * 63 + "-"],
)
def test_invalid_ids_are_rejected(store: ArtifactStore, bad_id: str) -> None:
    with pytest.raises(StoreError):
        store.open(bad_id)
    assert store.exists(bad_id) is False


def test_missing_artifact_raises(store: ArtifactStore) -> None:
    missing = "0" * 64
    with pytest.raises(StoreError):
        store.open(missing)
    with pytest.raises(StoreError):
        store.read_bytes(missing)
    with pytest.raises(StoreError):
        store.size(missing)
    assert store.exists(missing) is False


def test_size_and_exists(store: ArtifactStore) -> None:
    artifact_id = store.put_bytes(b"12345")
    assert store.size(artifact_id) == 5
    assert store.exists(artifact_id) is True


def test_max_bytes_blocks_put_bytes(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "small", max_bytes=10)
    with pytest.raises(StoreError):
        store.put_bytes(b"x" * 11)
    assert store.put_bytes(b"x" * 10)


def test_max_bytes_blocks_put_file(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "small", max_bytes=10)
    source = tmp_path / "big.bin"
    source.write_bytes(b"y" * 50)
    with pytest.raises(StoreError):
        store.put_file(source)
    # the source is untouched and no temporary files are left behind
    assert source.read_bytes() == b"y" * 50
    assert list(store.root.iterdir()) == []


def test_verify_is_true_for_untouched_artifact(store: ArtifactStore) -> None:
    artifact_id = store.put_bytes(b"verify me")
    assert store.verify(artifact_id) is True


def test_verify_detects_modified_artifact(store: ArtifactStore) -> None:
    artifact_id = store.put_bytes(b"verify me")
    target = store.root / artifact_id[:2] / artifact_id
    target.write_bytes(b"tampered!!")
    assert store.verify(artifact_id) is False


def test_store_open_refuses_symlinked_artifact(store: ArtifactStore, tmp_path: Path) -> None:
    artifact_id = store.put_bytes(b"payload")
    target = store.root / artifact_id[:2] / artifact_id
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"other")
    target.unlink()
    try:
        os.symlink(outside, target)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"symlinks are not available here: {exc}")
    with pytest.raises(StoreError):
        store.open(artifact_id)


def test_confine_accepts_plain_file_name(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "report.txt"
    target.write_text("hello", encoding="utf-8")
    resolved = confine(root, "report.txt")
    assert resolved == target.resolve()
    assert resolved.is_file()


@pytest.mark.parametrize(
    "name",
    ["../x", "a/b", "a\\b", ".hidden", "..", "", "  ", "sub/../x"],
)
def test_confine_rejects_bad_names(tmp_path: Path, name: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(StoreError):
        confine(root, name)


def test_confine_rejects_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    absolute = str(outside)
    with pytest.raises(StoreError):
        confine(root, absolute)


def test_confine_rejects_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(StoreError):
        confine(root, "missing.txt")


def test_confine_rejects_directory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "folder").mkdir(parents=True)
    with pytest.raises(StoreError):
        confine(root, "folder")


def test_confine_rejects_symlink_escaping_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = root / "link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"symlinks are not available here: {exc}")
    with pytest.raises(StoreError):
        confine(root, "link.txt")
