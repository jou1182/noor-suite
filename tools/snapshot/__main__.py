"""Command line entry point for the private snapshot pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import PLATFORMS, SnapshotError, fingerprint, importer, scan, selection, stage, verify

REPO = Path(__file__).resolve().parents[2]


class OpaqueArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SnapshotError("usage error")


def main(argv: list[str] | None = None) -> int:
    parser = OpaqueArgumentParser(prog="python -m tools.snapshot")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=OpaqueArgumentParser)
    for name in ("stage", "select", "scan", "mark-sanitized", "fingerprint", "import", "verify"):
        cmd = commands.add_parser(name)
        if name == "verify":
            group = cmd.add_mutually_exclusive_group(required=True)
            group.add_argument("--platform", choices=PLATFORMS)
            group.add_argument("--all", action="store_true")
        else:
            cmd.add_argument("--platform", choices=PLATFORMS, required=True)
        if name in ("select", "scan", "mark-sanitized", "fingerprint", "import"):
            cmd.add_argument("--stamp", required=True)
        if name == "stage":
            group = cmd.add_mutually_exclusive_group(required=True)
            group.add_argument("--from-git")
            group.add_argument("--from-dir")
            cmd.add_argument("--commit")
        if name == "mark-sanitized":
            cmd.add_argument("--list", required=True)
        if name == "fingerprint":
            cmd.add_argument("--source-label", required=True)
            cmd.add_argument("--source-commit")
            cmd.add_argument("--exposure", action="append", default=[])
            cmd.add_argument("--reviewed-by", required=True)
    try:
        args = parser.parse_args(argv)
        if args.command == "stage":
            message, code = stage.run(REPO, args.platform, args.from_dir, args.from_git, args.commit), 0
        elif args.command == "select":
            message, code = selection.run(REPO, args.platform, args.stamp), 0
        elif args.command == "scan":
            message, code = scan.run(REPO, args.platform, args.stamp)
        elif args.command == "mark-sanitized":
            message, code = scan.mark(REPO, args.platform, args.stamp, args.list), 0
        elif args.command == "fingerprint":
            message, code = fingerprint.run(REPO, args.platform, args.stamp, args.source_label,
                                            args.source_commit, args.exposure, args.reviewed_by), 0
        elif args.command == "import":
            message, code = importer.run(REPO, args.platform, args.stamp), 0
        elif args.all:
            message, code = verify.all_manifests(REPO)
        else:
            message, code = verify.run(REPO, args.platform)
    except SnapshotError as exc:
        print(f"snapshot error: {exc}", file=sys.stderr)
        return exc.code
    except Exception:
        print("snapshot error: operation failed", file=sys.stderr)
        return 2
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
