"""Copy a source into private staging with safe archive extraction."""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import SnapshotError, now, paths, write_state


def _safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name or "\t" in name or "\n" in name or "\r" in name or ".." in path.parts:
        raise ValueError("unsafe archive member")
    return path


def extract_archive(data: bytes, target: Path) -> None:
    """Extract only regular files and directories from git archive bytes."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive:
            rel = _safe_name(member.name)
            if not (member.isfile() or member.isdir()):
                raise ValueError("unsupported archive member")
            dest = target.joinpath(*rel.parts)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("unreadable archive member")
                with source, dest.open("wb") as output:
                    shutil.copyfileobj(source, output)


def _copy_regular(source: Path, dest: Path) -> None:
    if source.is_symlink():
        raise ValueError("symlink source")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlink source")
        if path.is_file():
            target = dest / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def run(repo: Path, platform: str, source_dir: str | None, git_dir: str | None,
        commit: str | None) -> str:
    stage_base, reports_base = paths(repo, platform)
    if bool(source_dir) == bool(git_dir) or (git_dir and not commit):
        raise SnapshotError("choose one source")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    target, private = paths(repo, platform, stamp)
    if target.exists() or private.exists():
        raise SnapshotError("stamp already exists")
    source = Path(git_dir or source_dir or "").resolve()
    if not source.is_dir():
        raise SnapshotError("source directory unavailable")
    target.mkdir(parents=True)
    try:
        if git_dir:
            git_executable = shutil.which("git")
            if git_executable is None:
                raise SnapshotError("git executable unavailable")
            git_executable = str(Path(git_executable).resolve())
            result = subprocess.run(  # noqa: S603 - fixed git argv, no shell; commit is one argument
                [git_executable, "-C", str(source), "archive", "--format=tar", commit],
                                    capture_output=True, check=False, timeout=120)
            if result.returncode:
                raise SnapshotError("git archive failed")
            extract_archive(result.stdout, target)
        else:
            _copy_regular(source, target)
    except Exception:
        shutil.rmtree(target)
        raise
    files = [p for p in target.rglob("*") if p.is_file()]
    write_state(private, {"status": "staged", "source_kind": "git" if git_dir else "dir",
                          "source_path": str(source), "source_commit": commit,
                          "copied_at": now(), "approvals": {}})
    return f"stamp: {stamp}\nfiles: {len(files)}\nbytes: {sum(p.stat().st_size for p in files)}"
