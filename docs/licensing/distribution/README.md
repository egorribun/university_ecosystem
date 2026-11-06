# Distribution notices and source access

The project notice governs only the original material it defines. Dependencies,
earlier publications and separately licensed adapters retain their own grants.
These files preserve upstream texts and source directions; their presence is
not a warranty that every rights/provenance item in the
[audit](../AUDIT-2026-11-06.md) is resolved.

| Distribution                             | Notices/source directions                                                                                                                                                                               |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python project wheel/source package      | Root `LICENSE`, `THIRD_PARTY_NOTICES.md`, transition/legacy notice, emoji notice, `PYTHON-LICENSES.txt` and `PYTHON-SOURCES.md` are declared as license files                                           |
| Native `rust_ext` wheel                  | `native/rust_ext/LICENSE`, `LICENSE-THIRD-PARTY`, `LICENSE-THIRD-PARTY-SOURCES.md`                                                                                                                      |
| Backend image                            | Project notices under `/app`; Python dependency texts and versioned sources in `/app/docs/licensing/distribution`; installed venv retains dependency license directories and the native wheel's notices |
| Frontend image                           | Project notices under `/app`, dependency records under `/app/docs/licensing/distribution`, browser notices in `dist/client/licenses`, and WASM package notices in both package directories              |
| Browser                                  | `/licenses/NOTICE.txt`, linked from the footer; font texts, JavaScript dependency notices/source indexes, both WASM notice/source indexes                                                               |
| WASM npm packages                        | `LICENSE`, `LICENSE-THIRD-PARTY` and `LICENSE-THIRD-PARTY-SOURCES.md`; npm packing is tested after build finalization and provenance binding                                                            |
| Gateway / ws-hub / file-processor images | `/usr/share/licenses/university-ecosystem/`: project notice, project third-party summary, corresponding `GO-DEPENDENCIES.txt` and `GO-SOURCES.tsv`                                                      |
| Custom Caddy image                       | Same license directory, with context-local project `LICENSE`, `THIRD_PARTY_NOTICES.txt` and `GO-SOURCES.tsv`                                                                                            |
| Docker socket log proxy image            | Same license directory: project notice/summary and its Go standard-library/vendor `GO-DEPENDENCIES.txt`; it has no external Go module imports                                                           |
| uni-cli binary                           | Distribute `LICENSE` and `GO-UNI-CLI.txt` alongside the binary; the source index is `GO-SOURCES.tsv`                                                                                                    |
| Parent Helm chart                        | Project `LICENSE`, original NATS chart archive and its accompanying `THIRD_PARTY_NOTICES.txt`                                                                                                           |
| Local Redis compatibility chart          | Project `LICENSE`, also included in the repackaged local dependency archive                                                                                                                             |

Every Rust/WASM/native package also includes `LICENSE-RUST-STD`,
`LICENSE-RUST-STD-COPYRIGHT.txt` and `LICENSE-RUST-STD-SOURCES.md` for the
pinned Rust 1.99.0 library/runtime notices. The original release-generated
HTML copyright record is preserved byte-for-byte under the `.txt` filename.
The website shares that corpus in `/licenses/rust-stdlib/`. The native wheel
retains both Windows and Linux crate notices and the historical Apache option.

The Go corpus consists of `GO-GATEWAY.txt`, `GO-WS-HUB.txt`,
`GO-FILE-PROCESSOR.txt`, `GO-CADDY.txt`, `GO-UNI-CLI.txt` and
`GO-DOCKER-LOG-PROXY.txt`. The source index uses public, versioned Go module
archives with the module proxy's required uppercase escaping. Go 1.26.10 source
is available from [the official source archive](https://go.dev/dl/go1.26.10.src.tar.gz).
The file-processor corpus includes its separately rebuilt health probe.
Nexus's later MIT notice and exact-tag evidence limit are retained there.

`PYTHON-LICENSES.txt` and `PYTHON-SOURCES.md` cover the platform runtime package
union and orjson's linked vendored Rust crates. The clamd notice/version gap is
explicit. MPL source access and LGPL replacement/relinking and related rights
must remain available under those component terms. Installed library licenses
are retained; do not strip their license directories from wheels/venvs. Review
the selected binary wheel's bundled native libraries before redistribution.

The JavaScript source index records five unresolved full-text notices and
host-absent optional variants. Linux optional-tooling notices include upstream
Sharp/libvips disclosures and Lightning CSS texts. This does not imply that
development tools or every optional native binary are delivered to a browser.

Regenerate notices from the selected lock/source artifacts whenever versions,
target platforms, imports, build tags, binary probe pins or toolchains change.
Preserve upstream legal text exactly. Generated indexes may normalize paths
and omit duplicate integrity fields; authoritative dependency/image pins stay
in the actual lockfiles and source declarations. New unresolved evidence must
stay visible rather than being replaced with a guessed SPDX identifier.
