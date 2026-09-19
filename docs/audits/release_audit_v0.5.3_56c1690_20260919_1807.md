# Release Audit Ledger
**Version:** 0.5.3
**Commit Hash:** 56c1690
**Timestamp:** 20260919_1807
**Agent:** Advisory Auditor

## 1. License Summary
Out of 39 total dependencies, 100% use permissive or standard open-source licenses: 23 MIT/MIT-0, 9 BSD (2/3-Clause), 5 Apache (2.0/Software License), 1 Mozilla Public License 2.0 (MPL 2.0), and 1 PSF-2.0.

**Flagged/Restrictive Licenses:**
- None Detected

## 2. Vulnerability Scan (pip-audit)
**Status:** Pass (0 vulnerabilities)

## 3. Security Scan (Gitleaks)
**Scan Type:** Full History (`gitleaks detect --redact`)
**Status:** Pass (no findings detected)

## 4. Repository Exposure Review
**Status:** Suspicious Files Detected

The following tracked files match the exposure review criteria (data exports and screenshots) and require Product Owner review:

**Data Exports (`.csv`):**
- `docs/sample/openrouter_activity_2026-08-24.csv`
- `docs/sample/openrouter_activity_2026-09-15.csv`

**Screenshots/Recordings (`.png`):**
- `docs/images/MCP Inspector_price_change.png`
- `docs/images/ZDR example Qwen3.8/Screenshot 2026-09-15 at 12.49.53 PM.png`
- `docs/images/ZDR example Qwen3.8/Screenshot 2026-09-15 at 12.50.24 PM.png`
