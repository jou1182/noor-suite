"""Build a local identity profile with ``python -m noor_identity build``."""

import argparse

from .build import build_identity


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build"])
    parser.add_argument("--identity-dir", required=True)
    args = parser.parse_args()
    build_identity(args.identity_dir)


if __name__ == "__main__":
    main()
