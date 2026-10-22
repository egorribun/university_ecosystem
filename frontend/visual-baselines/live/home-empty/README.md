# Approved Home12 visual baseline

Owner-approved on 2026-10-09 for manual visual comparison. The package is bound to the source SHA and Linux Chromium capture provenance in approval.json.

It contains only the 12 approved PNGs and curated provenance. Private capture sidecars, raw manifest, logs, and machine-local paths are intentionally excluded.

Provenance identifies the source with its full GitHub commit URL. Manifest and PNG checksums use `sha256:<lowercase hex>` digests; compare the hexadecimal suffix with the SHA-256 of the original bytes.

This is a manual comparison baseline. The existing mocked Windows Playwright snapshot test does not consume it, and this package does not claim an automated visual regression check.
