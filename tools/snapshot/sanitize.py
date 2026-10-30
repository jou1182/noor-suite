"""Apply explicit text-only rules inside a private stage."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

from noor_contracts.validate import validate

from tools import scan_public_repo as scanner
from tools.name_replacement import replacement_pattern

from . import SnapshotError, now, paths, read_state, write_json, write_state
from .fingerprint import inventory
from .selection import glob_match


def _profile() -> str:
    location = os.environ.get("NOOR_IDENTITY_DIR")
    if not location:
        raise SnapshotError("NOOR_IDENTITY_DIR is not set")
    root = Path(location).resolve()
    try:
        profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
        validate(profile, "identity-profile")
        return profile["short_name"]
    except Exception:
        raise SnapshotError("identity profile invalid") from None


def _rules(repo: Path, platform: str) -> list[dict]:
    file = repo / "tools" / "snapshot" / "rules" / f"{platform}.json"
    if not file.is_file():
        raise SnapshotError("rules unavailable", 1)
    try:
        rules = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(rules, list) or not rules:
            raise ValueError
        for rule in rules:
            if (not isinstance(rule, dict) or not re.fullmatch(r"[a-z0-9-]+", rule["id"])
                    or not re.fullmatch(r"N\d+", rule["decision"])
                    or rule["kind"] not in ("replace", "forbid", "identity")
                    or not isinstance(rule["files"], list) or not rule["files"]
                    or not all(isinstance(x, str) and x for x in rule["files"])):
                raise ValueError
            if rule["kind"] != "identity":
                re.compile(rule["pattern"])
            if rule["kind"] == "replace":
                if not isinstance(rule["replacement"], str) or set(rule["expect"]) not in ({"exact"}, {"min"}):
                    raise ValueError
                if not all(isinstance(x, int) and x >= 0 for x in rule["expect"].values()):
                    raise ValueError
                if "keep_group" in rule and (not isinstance(rule["keep_group"], int)
                                             or isinstance(rule["keep_group"], bool)
                                             or not 1 <= rule["keep_group"] <= re.compile(rule["pattern"]).groups):
                    raise ValueError
                if "done_pattern" in rule:
                    re.compile(rule["done_pattern"])
                if "done_check" in rule:
                    _check_spec(rule["done_check"])
        return rules
    except (OSError, ValueError, KeyError, TypeError, re.error):
        raise SnapshotError("rules invalid", 1) from None


def _text(data: bytes) -> tuple[str, bytes] | None:
    if any(byte < 32 and byte not in (9, 10, 12, 13) for byte in data):
        return None
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    try:
        return data[len(bom):].decode("utf-8"), bom
    except UnicodeDecodeError:
        return None


def _check_spec(check: dict) -> None:
    """done_check: {"environ_key_contains": s} or {"call": attr, "keyword": k, "value": v}."""
    if set(check) == {"environ_key_contains"} and isinstance(check["environ_key_contains"], str):
        return
    if (set(check) == {"call", "keyword", "value"} and isinstance(check["call"], str)
            and isinstance(check["keyword"], str) and type(check["value"]) in (str, int)):
        return
    raise ValueError


def _ast_count(value: str, check: dict) -> int:
    """Count executable call sites only; strings and comments never count. Unparsable ⇒ 0."""
    try:
        tree = ast.parse(value)
    except (SyntaxError, ValueError):
        return 0
    if "environ_key_contains" in check:
        part = check["environ_key_contains"].casefold()
        return sum(1 for node in ast.walk(tree)
                   if isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ"
                   and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)
                   and part in node.slice.value.casefold())
    values = [k.value for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == check["call"]
              for k in node.keywords if k.arg == check["keyword"]]
    # Every call that sets the keyword must hold the literal target; a variable or another value
    # (e.g. a live call beside a dead one) fails closed, and the owner adjusts the rule.
    if not all(isinstance(v, ast.Constant) and type(v.value) is type(check["value"])
               and v.value == check["value"] for v in values):
        return -1
    return len(values)


def _case_like(found: str, value: str) -> str:
    """Keep a Latin identifier's case style: OLD ⇒ NOOR, OldName ⇒ NoorName, old_x ⇒ noor_x."""
    if not value.isascii() or not found[:1].isalpha():
        return value
    letters = [c for c in found if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return value.upper()
    return value[:1].upper() + value[1:] if found[0].isupper() else value


def _active_lines(value: str) -> str:
    """Exclude comment-only lines from completed-replacement evidence."""
    return "\n".join(line for line in value.splitlines() if not line.lstrip().startswith("#"))


def run(repo: Path, platform: str, stamp: str) -> tuple[str, int]:
    target, private = paths(repo, platform, stamp)
    state = read_state(private)
    if state.get("status") in ("fingerprinted", "publishing", "imported"):
        raise SnapshotError("sanitize refused after fingerprint", 1)
    rules = _rules(repo, platform)
    rules_hash = hashlib.sha256((repo / "tools" / "snapshot" / "rules" / f"{platform}.json").read_bytes()).hexdigest()
    files: dict[str, tuple[Path, str, bytes]] = {}
    skipped = 0
    for file in target.rglob("*"):
        if file.is_symlink():
            raise SnapshotError("symlink in stage", 1)
        if not file.is_file():
            continue
        content = _text(file.read_bytes())
        if content is None:
            skipped += 1
        else:
            files[file.relative_to(target).as_posix()] = (file, *content)
    names: list[str] = []
    short_name = ""
    if any(rule["kind"] == "identity" for rule in rules):
        try:
            names = scanner.load_blocklist(repo, True)
        except scanner.ConfigError:
            raise SnapshotError("blocklist unavailable") from None
        if not names:
            raise SnapshotError("blocklist empty")
        short_name = _profile()
    report = []
    lines = []
    failed = False
    changed: set[str] = set()
    for rule in rules:
        identity = (replacement_pattern(names, short_name, "noor", loose=rule.get("loose") is True)
                    if rule["kind"] == "identity" else None)
        matcher = identity[0] if identity else re.compile(rule["pattern"])
        counts: dict[str, int] = {}
        done: dict[str, int] = {}
        count = 0
        for rel, (file, value, bom) in files.items():
            if not any(glob_match(rel, pattern) for pattern in rule["files"]):
                continue
            if rule["kind"] == "replace":
                # keep_group re-emits a captured prefix, so rules need no "\g<n>" (the scanner reads a
                # backslash after a quote as a UNC path).
                def keep(match: re.Match[str], rule: dict = rule) -> str:
                    prefix = match.group(rule["keep_group"])
                    if prefix is None:
                        raise SnapshotError(f"keep_group unmatched: {rule['id']}", 1)
                    return prefix + match.expand(rule["replacement"])
                result, amount = matcher.subn(rule["replacement"] if "keep_group" not in rule else keep, value)
                if "done_check" in rule:
                    done[rel] = _ast_count(result, rule["done_check"])
                elif "done_pattern" in rule:
                    done[rel] = len(re.findall(rule["done_pattern"], _active_lines(result)))
            elif rule["kind"] == "identity":
                result, amount = matcher.subn(
                    lambda match, values=identity[1]: _case_like(match.group(), values[match.lastgroup]), value)
            else:
                result, amount = value, len(matcher.findall(value))
            counts[rel] = amount
            count += amount
            if result != value:
                files[rel] = (file, result, bom)
                changed.add(rel)
        if rule["kind"] == "replace":
            expected = rule["expect"]
            # done_check proves the executable result on every run, not only on reruns.
            observed = (-1 if any(value < 0 for value in done.values()) else sum(done.values())
                        if "done_check" in rule else count if count else sum(done.values()))
            ok = (observed == expected["exact"] if "exact" in expected
                  else observed >= expected["min"])
        elif rule["kind"] == "identity":
            remaining = sum(len(matcher.findall(value)) for rel, (_, value, _) in files.items()
                            if any(glob_match(rel, pattern) for pattern in rule["files"]))
            ok = remaining == 0
        else:
            ok = count == 0
        status = "ok" if ok else "info" if rule.get("blocking") is False else "mismatch"
        failed |= status == "mismatch"
        report.append({"id": rule["id"], "decision": rule["decision"], "status": status,
                       "count": count, "per_file": counts, "already_applied": done})
        lines.append(f"{rule['id']} {rule['decision']} {status} count={count}")
    for rel in changed:
        file, value, bom = files[rel]
        file.write_bytes(bom + value.encode("utf-8"))
    if changed:
        state["status"] = "staged"
        state.pop("scan_hashes", None)
    state["sanitize"] = {"rules_sha256": rules_hash,
                         "rules": [{"id": item["id"], "status": item["status"], "count": item["count"]}
                                   for item in report],
                         "post_hashes": {item["path"]: item["sha256"] for item in inventory(target)}}
    write_state(private, state)
    write_json(private / f"sanitize-{now().replace(':', '').replace('+', '-')}.json",
               {"rules": report, "files_changed": sorted(changed), "files_skipped": skipped})
    lines.extend((f"files changed: {len(changed)}", f"files skipped: {skipped}"))
    return "\n".join(lines), 1 if failed else 0
