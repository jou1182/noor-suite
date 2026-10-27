# Public export hardening

## Symptom and scope

The public exporter followed selected links and included untracked files without an explicit review gate. The first commit was not covered by the CI diff scan. Fresh clone setup and rights were unclear.

## Requirements and acceptance

- Selected files remain within the repository and contain no symlink or junction component; failed exports leave no output folder.
- Untracked selected files are counted and listed beside the output. Export requires `--include-untracked` when the count is nonzero.
- A required private blocklist replaces names in exported UTF-8 text only. The source remains unchanged; binary and text line endings are preserved. A post-export name check and repository scan must pass.
- CI scans `main` and scans the full tree on the first commit.
- README gives runnable fresh-clone steps, and the rights notice is explicit.

The owner's export operation remains outside this implementation task. Tests use synthetic repositories and blocklists.
