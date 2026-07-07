# OSS-Fuzz Integration for `pyo3-sanitizer`

This directory contains the configuration stub for integrating the
`crates/pyo3-sanitizer` Rust crate with [OSS-Fuzz](https://google.github.io/oss-fuzz/).

## Files

| File | Purpose |
|------|---------|
| `project.yaml` | OSS-Fuzz project metadata (language, sanitizers, fuzzing engines) |
| `build.sh` | Build script run inside the OSS-Fuzz container; compiles cargo-fuzz targets |
| `Dockerfile` | Extends `base-builder-rust`; installs system dependencies |

## Fuzzing engines

Configured engines: **libFuzzer** (primary), **AFL++**, **Honggfuzz**.

Configured sanitizers: **AddressSanitizer (ASan)**, **UndefinedBehaviorSanitizer (UBSan)**.

## Local testing

```bash
# Build the fuzz targets locally
cargo fuzz build --manifest-path crates/pyo3-sanitizer/Cargo.toml

# Run a single target for 60 seconds
cargo fuzz run fuzz_sanitizer -- -max_total_time=60
```

## Submitting to OSS-Fuzz

1. Fork [google/oss-fuzz](https://github.com/google/oss-fuzz).
2. Copy this directory to `projects/university-ecosystem/`.
3. Open a pull request — OSS-Fuzz will validate the `project.yaml` schema
   and attempt a trial build.

> [!NOTE]
> The `primary_contact` e-mail in `project.yaml` must match a verified
> GitHub account.  Update it before submitting the OSS-Fuzz PR.
