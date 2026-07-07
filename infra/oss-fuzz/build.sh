#!/bin/bash
# OSS-Fuzz build script for pyo3-sanitizer fuzz targets
set -e

cd "$SRC/university_ecosystem"
cargo fuzz build --release 2>/dev/null || true

# Copy fuzz targets to $OUT
for fuzzer in $(cargo fuzz list 2>/dev/null); do
    cp target/x86_64-unknown-linux-gnu/release/$fuzzer "$OUT/" 2>/dev/null || true
done
