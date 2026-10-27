# Repair plan

Validate selected paths before output creation. Emit an untracked manifest, then enforce the flag. Copy the allowlisted files, transform UTF-8 text in place in the output, verify names, and invoke the existing scanner. Remove a created output folder on any failure. Keep scanner invocation replaceable in unit tests. Update CI fallback, setup instructions, rights notice, and the scanner-triggering comment. No data model or external interface changes beyond the new exporter flag and manifest.

Validation: synthetic exporter tests, the specified Python and Node suites, and the targeted repository scan. The project constitution's security, test, and documentation principles apply without deviation.

## Amendment: export scan and name variants (2026-10-27)

The first owner-run export removed its output after the scan found issues. Staging mode did not apply this repository's reviewed scanner exceptions and binary pins. Run the source scanner with `--repo` from the output folder, so it applies the exported repository configuration; first verify that the scanner and allowlist in the output are byte-identical to their source copies. Import the scanner's own name variant and hit functions for export-time replacement and verification, including every exported path component. Bound replacements to whole words, preserve line breaks, and apply only the reviewed public wording cleanups afterward. Keep the output cleanup rule and synthetic-only test approach.
