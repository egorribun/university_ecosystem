# Rust 1.99.0 standard-library notice sources

These notice inputs cover the Rust standard-library source used by native Windows/Linux and `wasm32-unknown-unknown` artifacts compiled with Rust 1.99.0. They are version-bound to the installed compiler's official Rust source commit.

## Exact source and package metadata

- Rust compiler observed: `rustc 1.99.0 (b940084d7 2026-09-28)`; exact source tree: [Rust source at release commit](https://github.com/rust-lang/rust/tree/1.99.0).
- Root [COPYRIGHT](https://github.com/rust-lang/rust/blob/1.99.0/COPYRIGHT), [LICENSE-APACHE](https://github.com/rust-lang/rust/blob/1.99.0/LICENSE-APACHE), and [LICENSE-MIT](https://github.com/rust-lang/rust/blob/1.99.0/LICENSE-MIT) are included verbatim in `LICENSE-RUST-STD`.
- Exact [core manifest](https://github.com/rust-lang/rust/blob/1.99.0/library/core/Cargo.toml), [alloc manifest](https://github.com/rust-lang/rust/blob/1.99.0/library/alloc/Cargo.toml), and [std manifest](https://github.com/rust-lang/rust/blob/1.99.0/library/std/Cargo.toml) declare `MIT OR Apache-2.0`. `alloc` depends on `compiler_builtins`. The exact [compiler_builtins manifest](https://github.com/rust-lang/rust/blob/1.99.0/library/compiler-builtins/compiler-builtins/Cargo.toml) declares `MIT AND Apache-2.0 WITH LLVM-exception AND (MIT OR Apache-2.0)`. The Apache, MIT, LLVM-exception, and Unicode-3.0 text bodies are included in the addendum.
- The Windows host distribution contains `rust-std-x86_64-pc-windows-msvc` and `rust-std-wasm32-unknown-unknown`; the same release's library notice document, [Rust 1.99.0 Windows distribution archive](https://static.rust-lang.org/dist/rust-1.99.0-x86_64-pc-windows-msvc.tar.xz), supplies the byte-exact notice retained as `LICENSE-RUST-STD-COPYRIGHT.txt`. In that archive it is `share/doc/rust/COPYRIGHT-library.html`. It is the upstream release-generated library-only notice, not the whole compiler/toolchain `COPYRIGHT.html`.

## Target-specific limits

The exact standard-library manifests show `windows-link` as a Windows-only std dependency and `dlmalloc` for `wasm32-unknown-unknown`; `libc` is a non-MSVC native dependency. `COPYRIGHT-library.html` records the release's in-tree exceptions and out-of-tree standard-library crate notices across its supported target set, including source URLs and notice bodies. Its dependency list is a release-wide library scope, not a target-filtered proof that every listed crate is linked into each of these three artifacts. This audit did not download the Rust source component or rebuild the standard library to derive narrower per-target link closures.

The generated `COPYRIGHT-library.html` identifies the in-tree Unicode-3.0 exception and a BSD-2-Clause Fuchsia file; only the Unicode text is in the addendum because Fuchsia is outside the audited Windows/Linux/wasm32 targets. Other target-specific and out-of-tree notices remain available in the exact release `COPYRIGHT-library.html` companion.

The original release-generated HTML notice is retained byte-for-byte in `LICENSE-RUST-STD-COPYRIGHT.txt` (a text filename preserves its contents without reformatting). The accompanying `LICENSE-RUST-STD` file retains the core license bodies.
