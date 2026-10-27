"""Tests for :mod:`noor_registry.runners` (T026/T027)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from noor_registry.runners import RunResult, ToolError, run_tool


def tool(code: str) -> list[str]:
    """Build an argv that runs ``code`` with the current interpreter."""

    return [sys.executable, "-c", code]


def test_success_returns_run_result(tmp_path: Path) -> None:
    code = "import json; print(json.dumps({'ok': True, 'n': 7}))"
    result = run_tool(tool(code), timeout=30, env={}, cwd=tmp_path)
    assert isinstance(result, RunResult)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["n"] == 7


def test_nonzero_exit_raises_tool_error(tmp_path: Path) -> None:
    code = "import sys; sys.stderr.write('boom happened'); sys.exit(3)"
    with pytest.raises(ToolError) as excinfo:
        run_tool(tool(code), timeout=30, env={}, cwd=tmp_path)
    error = excinfo.value
    assert error.reason == "nonzero_exit"
    assert error.returncode == 3
    assert "boom happened" in str(error)


def test_timeout_raises_tool_error(tmp_path: Path) -> None:
    code = "import time; time.sleep(30)"
    with pytest.raises(ToolError) as excinfo:
        run_tool(tool(code), timeout=0.5, env={}, cwd=tmp_path)
    assert excinfo.value.reason == "timeout"


def test_environment_is_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOOR_SENTINEL_LEAK", "sentinel-value")
    code = (
        "import json, os;"
        "print(json.dumps({"
        "'sentinel': os.environ.get('NOOR_SENTINEL_LEAK'),"
        "'caller': os.environ.get('NOOR_CALLER_VALUE'),"
        "'path': os.environ.get('PATH')}))"
    )
    result = run_tool(
        tool(code),
        timeout=30,
        env={"NOOR_CALLER_VALUE": "caller-value"},
        cwd=tmp_path,
    )
    payload = json.loads(result.stdout)
    assert payload["sentinel"] is None
    assert payload["caller"] == "caller-value"
    assert payload["path"]


def test_caller_env_overrides_inherited_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONIOENCODING", "latin-1")
    code = "import os; print(os.environ.get('PYTHONIOENCODING'))"
    result = run_tool(
        tool(code), timeout=30, env={"PYTHONIOENCODING": "utf-8"}, cwd=tmp_path
    )
    assert result.stdout.strip() == "utf-8"


def test_stdin_is_closed(tmp_path: Path) -> None:
    code = "import sys; data = sys.stdin.read(); print(len(data))"
    result = run_tool(tool(code), timeout=30, env={}, cwd=tmp_path)
    assert result.stdout.strip() == "0"


def test_cwd_is_used(tmp_path: Path) -> None:
    code = "import os; print(os.getcwd())"
    result = run_tool(tool(code), timeout=30, env={}, cwd=tmp_path)
    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()


def test_argv_as_string_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as excinfo:
        run_tool("echo hello", timeout=30, env={}, cwd=tmp_path)
    assert excinfo.value.reason == "bad_args"


def test_empty_argv_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as excinfo:
        run_tool([], timeout=30, env={}, cwd=tmp_path)
    assert excinfo.value.reason == "bad_args"


def test_non_string_argv_entry_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as excinfo:
        run_tool([sys.executable, 42], timeout=30, env={}, cwd=tmp_path)
    assert excinfo.value.reason == "bad_args"


def test_missing_executable_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as excinfo:
        run_tool(["noor_missing_tool_xyz"], timeout=30, env={}, cwd=tmp_path)
    assert excinfo.value.reason == "not_found"


def test_oversized_output_is_rejected(tmp_path: Path) -> None:
    code = "print('x' * 5000)"
    with pytest.raises(ToolError) as excinfo:
        run_tool(tool(code), timeout=30, env={}, cwd=tmp_path, max_output=100)
    assert excinfo.value.reason == "output_too_large"


def test_failure_does_not_return_partial_result(tmp_path: Path) -> None:
    code = "import sys; print('partial'); sys.exit(4)"
    with pytest.raises(ToolError):
        run_tool(tool(code), timeout=30, env={}, cwd=tmp_path)


def test_guarded_parent_keeps_child_guarded(tmp_path, monkeypatch):
    monkeypatch.setenv("NOOR_NETGUARD", "1")
    result = run_tool(
        [sys.executable, "-c", "import os; print(os.environ.get('NOOR_NETGUARD'))"],
        timeout=30,
        env={"NOOR_NETGUARD": "0"},
        cwd=tmp_path,
    )
    assert result.stdout.strip() == "1"


def test_not_found_message_has_no_directory(tmp_path):
    missing = str(tmp_path / "no-such-tool.exe")
    with pytest.raises(ToolError) as excinfo:
        run_tool([missing], timeout=5, env={}, cwd=tmp_path)
    assert str(tmp_path) not in str(excinfo.value)
