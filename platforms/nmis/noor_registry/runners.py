"""Run helper tools as isolated child processes.

The runner never uses a shell, never inherits the full environment and always
reports failures through :class:`ToolError` -- a failed run never yields a
partial :class:`RunResult`.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = ["INHERITED_ENV_KEYS", "RunResult", "ToolError", "run_tool"]

#: The only variables inherited from the parent process.
INHERITED_ENV_KEYS: tuple[str, ...] = (
    "SYSTEMROOT",
    "PATH",
    "PYTHONPATH",
    "NODE_OPTIONS",
    "NOOR_NETGUARD",
    "TEMP",
    "TMP",
    "PYTHONIOENCODING",
)

#: Number of trailing stderr characters kept in an error message.
STDERR_TAIL_LIMIT = 2000


@dataclass(frozen=True)
class RunResult:
    """The successful outcome of a child process."""

    returncode: int
    stdout: str
    stderr: str


class ToolError(RuntimeError):
    """Raised when a tool could not be run, or failed."""

    def __init__(
        self,
        reason: str,
        message: str | None = None,
        *,
        returncode: int | None = None,
    ) -> None:
        super().__init__(message if message is not None else reason)
        self.reason = reason
        self.returncode = returncode


def run_tool(
    argv: list[str],
    *,
    timeout: float,
    env: Mapping[str, str],
    cwd: Path,
    max_output: int = 1_000_000,
) -> RunResult:
    """Run ``argv`` and return its :class:`RunResult`.

    ``argv`` is executed directly (never through a shell).  The child sees
    only the whitelisted parent variables plus the caller's ``env``.
    """

    _check_argv(argv)
    _check_timeout(timeout)
    _check_max_output(max_output)

    child_env = _build_env(env)

    try:
        completed = subprocess.run(  # noqa: S603 - shell=False, argv is a list
            list(argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            stdin=subprocess.DEVNULL,
            env=child_env,
            cwd=str(Path(cwd)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            "timeout", f"tool timed out after {timeout} seconds"
        ) from exc
    # Messages name the tool only by its file name: they may reach the UI, which shows no local paths.
    except FileNotFoundError as exc:
        raise ToolError(
            "not_found", f"tool executable not found: {Path(argv[0]).name}"
        ) from exc
    except NotADirectoryError as exc:
        raise ToolError("not_found", "tool working directory is invalid") from exc
    except OSError as exc:
        raise ToolError("bad_args", f"tool could not be started ({type(exc).__name__})") from exc

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if len(stdout) > max_output or len(stderr) > max_output:
        raise ToolError(
            "output_too_large",
            f"tool output exceeded the limit of {max_output} characters",
        )
    if completed.returncode != 0:
        tail = stderr[-STDERR_TAIL_LIMIT:]
        raise ToolError(
            "nonzero_exit",
            f"tool exited with status {completed.returncode}: {tail}",
            returncode=completed.returncode,
        )
    return RunResult(
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _check_argv(argv: list[str]) -> None:
    if isinstance(argv, (str, bytes)) or not isinstance(argv, (list, tuple)):
        raise ToolError("bad_args", "argv must be a non-empty list of strings")
    if len(argv) == 0:
        raise ToolError("bad_args", "argv must not be empty")
    for item in argv:
        if not isinstance(item, str) or not item:
            raise ToolError("bad_args", "argv entries must be non-empty strings")


def _check_timeout(timeout: float) -> None:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ToolError("bad_args", "timeout must be a number of seconds")
    if timeout <= 0:
        raise ToolError("bad_args", "timeout must be positive")


def _check_max_output(max_output: int) -> None:
    if isinstance(max_output, bool) or not isinstance(max_output, int):
        raise ToolError("bad_args", "max_output must be an integer")
    if max_output <= 0:
        raise ToolError("bad_args", "max_output must be positive")


def _build_env(env: Mapping[str, str]) -> dict[str, str]:
    if env is None:
        env = {}
    if not isinstance(env, Mapping):
        raise ToolError("bad_args", "env must be a mapping of strings to strings")
    child_env: dict[str, str] = {}
    for key in INHERITED_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            child_env[key] = value
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ToolError("bad_args", "env keys and values must be strings")
        child_env[key] = value
    # A guarded parent always yields a guarded child, whatever the caller passed.
    if os.environ.get("NOOR_NETGUARD") == "1":
        child_env["NOOR_NETGUARD"] = "1"
    return child_env
