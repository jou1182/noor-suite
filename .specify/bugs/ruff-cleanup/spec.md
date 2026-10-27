# Ruff cleanup

## Symptom and scope

The configured Ruff check reports 58 findings in `packages`, `platforms`, `tools`, and selected tests. Resolve every finding under the existing rule set and pin CI to the local Ruff version. Preserve runtime behavior except for genuine safety fixes.

## Acceptance

- The requested Ruff command reports zero findings.
- The specified Python and Node test suites pass.
- The public repository scan is clean for paths and secrets without reading the private name blocklist.
- Changes do not weaken Ruff configuration or add blanket suppressions.

## Assumptions

Existing fixture setup calls must still execute even where their return values are unused. Git subprocesses receive fixed argument lists and never invoke a shell. The private name blocklist is unavailable to this task.
