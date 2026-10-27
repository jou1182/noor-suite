# Snapshot allowlists

Create `<platform>.txt` on the platform's staging day. Use one repository-relative POSIX glob per line; `**` matches nested files. Blank lines and lines starting with `#` are ignored. An absent or empty allowlist stops selection. Hard-coded forbidden families are always removed, even when a glob matches them. Keep source-specific paths and private report content out of this directory.

Destination-root `SOURCE.md` is excluded from the snapshot tree. It is written after import, scanned during `verify`, and covered by the repository scan before commit. Verification fails when it exists but `NOOR_BLOCKLIST_FILE` is unset. A destination-root `.gitkeep`, if present, must be empty.

Import builds its checked tree in `.noor-import-<platform>-<stamp>` beside the repository, then moves the directory into `platforms/` in one operation. Remove a stale sibling directory before retrying. A private `publishing` state lets a retry finish writing the public manifest after an interrupted move.

For `mark-sanitized --list`, use one record per line: `<64-hex sha256> <kind> <reason...>`. Kinds are `visual` (binary asset reviewed), `path` (path finding confirmed non-sensitive), and `session` (session finding confirmed non-sensitive). The reason must have at least three characters. Blank lines and `#` comment lines are ignored. Review reasons stay in private state; command output uses counts only.
