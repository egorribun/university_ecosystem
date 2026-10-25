# React Compiler facade integration evidence

## First-party archive foundation (2026-10-25)

The [tracked source archive](../../frontend/vendor/react-compiler-zod-compat-1.0.0.tgz)
is an intentionally versioned, reproducible first-party source package, not an
opaque compiler or engine bundle. It contains only the four readable package
files. It is not yet activated as the legacy compiler dependency.

[Hosted producer job 121113577192](https://github.com/egorribun/university_ecosystem/actions/runs/40174667081/job/121113577192)
passed all **26 archive guards** and the live two-pack recipe. Producer head
was `3dfefdc53eb745098e8e02f867389d6e06a796d0`; actual checkout was merge
`665b889ddbf5eacca07141ba883d43d7bd3635aa`, with identical source tree
`a964c2160d3587923de4880961ce3a38a9f19a4c`.
Both packs produced the same **2853 bytes**, using Linux x64,
Node v24.21.0 and npm11.17.0 with scripts disabled and offline packing.
The four payloads total **5504 bytes**. Source/configuration/Git postflight
and temporary-workspace cleanup succeeded before candidate output.

Archive SHA-256: `3887a71e809e5c427392ee521eec91296bffae536aa11f8bd04863922a193ff5`.
Git blob SHA-1: `c67aa6c38e78bc2c96ccf5c3f8e30edebcaa5666`.
The candidate bytes and all four source hashes were independently compared
with the immutable Git sources before this foundation entry was prepared.

A blocking checkout readback step now checks the committed blob identity,
regular-file size, both hashes and four-source payload equality before
repacking. Its first hosted result on the foundation commit is still required;
the producer's success does not stand in for that checkout check.
The exact artifact path is protected in all three existing policy inventories.
No wildcard exclusion, peer-range change, lifecycle execution or graph update
is introduced.

A subsequent dependency candidate must use an immutable commit-qualified
archive URL, not the moving branch URL. The recipe, tests and four packaged
source files are unchanged from the verified producer. Adding this source
archive alone does not prove strict npm graph validity, final native compiler
resolution, production exclusion, Docker transfer, parity or vulnerability
closure. The later relative-file generator in the producer job still failed
strict npm ls independently; the tracked application manifest/lock remain
staged and the separate embedded Babel compiler risk remains open.


## Scope and status

[ADR-048](../adr/ADR-048-react-compiler-schema-compatibility.md) governs the
development-only compatibility boundary. The stable packaged
[README](../../frontend/scripts/react-compiler-zod-compat/README.md) describes
its identity and API; evolving graph, layout and acceptance records belong
here rather than in the four-file package payload.

At source `6ba0de220b497126f51d31b84653a2d1b5d35cb8`, the tracked manifest
and lock retain the staged local facade. The actual legacy compiler consumer
still uses its original Zod 3 dependency. At that checkpoint no final consumer graph or archive
foundation had been accepted. The root Zod 4.6.7 lock record remains
production-classified; a development-only facade is not proof that the whole
project has no production Zod dependency.

The relative-directory final-candidate experiment is not an accepted
alternative: the isolated strict installation and native resolution controls
do not override npm's `ELSPROBLEMS` invalid-edge result for
`file:../../scripts/react-compiler-zod-compat`. Do not waive that result,
spoof the facade's identity or add a relative-symlink workaround.

The foundation procedure is limited to a reproducible first-party
archive: exactly `package.json`, `index.cjs`, `LICENSE` and `README.md`,
packed twice by pinned npm 11.17.0 with scripts disabled and offline packing.
The recipe must verify bounded gzip/tar structure, every source byte,
archive hashes and npm summary, source/configuration/Git immutability and
temporary-workspace cleanup before emitting candidate bytes. The source
artifact path is `frontend/vendor/react-compiler-zod-compat-1.0.0.tgz`,
outside the package's files list. Tracking this archive does not activate it in the dependency graph.

A later, separate dependency candidate may use the exact immutable
same-repository HTTPS archive URL only after a reviewed foundation commit.
Registry publication, releases, credentials, compiler-bundle vendoring and
unreviewed graph changes are not part of this foundation. The manifest's
`private: true` flag prevents npm publication, not public-repository access.

## Preserved staged integration record

The following record was moved from the packaged README at source
`6ba0de220b497126f51d31b84653a2d1b5d35cb8`. It describes the staged
implementation and its verification requirements, not a current
vulnerability-closure certificate:

`legacy-baseline.json` preserves the complete observed pre-change report:
37 finite ESLint fixtures, installed artifact and formatter hashes, lock
integrity, source revision, and five schema/error-formatting observations.
It is a legacy behavioral baseline, not a vulnerability-closure certificate.

The staged dependency graph adds this local package and its fixed engine as
development-only dependencies. It deliberately leaves the actual rc.2
consumer and its Zod 3 dependency untouched until compatibility is proved.
A test-owned temporary module tree uses the unchanged, hash-checked rc.2
artifact and native Node resolution to test this facade plus the already
installed formatter 4.0.2. No source rewriting, evaluator, module loader hook,
package lifecycle patch or ad hoc installation is used.

The entire captured diagnostic/suppression/suggestion corpus must match.
Only wording of the two already rejected malformed-configuration exceptions
is separately reported for review; they must still throw ReactCompilerError
with the same InvalidConfig reason. ESLint 10 itself rejects function-valued
rule options before compiler invocation. The facade's callback semantics are
therefore also checked directly, including rejection before the callback runs.

The baseline includes intentional absences: default ref-access validation is
off in this old rule; a nested state-mutation fixture is silent even though
nested unused directives are reported. Do not claim a broader legacy guarantee
or silently replace these defaults with a newer compiler's behavior.

Fresh full and production dependency-graph checks, normal frontend CI, and
Docker builder-transfer tests remain required. The adapter is not copied into
the runtime image. The old Babel compiler's separately embedded pre-fix code
remains a distinct unresolved source-to-sink assessment.

## Source-bound checks

- [Frozen legacy baseline](../../frontend/scripts/react-compiler-zod-compat/legacy-baseline.json)
- [Facade and compiler parity tests](../../frontend/scripts/react-compiler-zod-compat.test.mjs)
- [Archive recipe guards](../../frontend/scripts/pack-react-compiler-zod-compat.test.mjs)
- [Final candidate guards](../../frontend/scripts/generate-react-compiler-final-lock-candidate.test.mjs)
- [Node dependency audit workflow](../../.github/workflows/reusable-security-audit.yml)

Preserve the 37 legacy fixtures and all existing compatibility controls.
A new source revision requires fresh evidence. An archive reproducibility
report alone does not prove strict npm graph validity, compiler parity,
normal frontend CI, production exclusion, Docker transfer or closure of the
separate embedded Babel compiler risk.
