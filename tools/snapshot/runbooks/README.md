# Snapshot owner runbook

Run `nmis_full.ps1 -SourceRepo <path> -Ref <commit>` for mode A. It stages a Git archive, selects, sanitizes, and scans. It stops at the first failing command and prints the stamp for manual review.

After reviewing private reports and building an approval list, run `nmis_full.ps1 -Finish -Stamp <stamp> -ApprovalList <path> -SourceLabel <label> -ReviewedBy <name>` for mode B. It records approvals, rescans so the approvals take effect, and fingerprints. The source label must be a substitute, never the private repository name. Add `-Exposure EXP-ID` for each closed exposure. Import waits for the separate T044 gate.

Every sanitization rule must be clean before fingerprinting, including informational rules. Mode A still runs the scan when an informational rule reports a finding; resolve it before mode B.

Command output is opaque: counts, rule IDs, statuses, and file IDs only. Never paste private reports, source paths, source references, file names, matched text, or approval reasons into shared logs.
