# Tasks

- [x] Record the lint symptom and acceptance criteria.
- [x] Apply and review safe Ruff fixes.
- [x] Correct remaining findings without changing lint policy.
- [x] Pin CI Ruff to 0.17.2.
- [x] Run and record Ruff, Python, Node, and public scanner gates.

## Verification (2026-10-28)

- Ruff 0.17.2: All checks passed.
- Requested Python suite: 550 passed, 9 skipped; one existing `asyncio_mode` config warning.
- Explicit Node `.mjs` files: 20 passed.
- Public scan: clean for paths and secrets with `NOOR_BLOCKLIST_FILE` unset; private names were not checked. Two binary assets remain listed for visual review.
- Additional vault test file: 9 passed.
