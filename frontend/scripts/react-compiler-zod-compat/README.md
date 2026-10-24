# React Compiler schema compatibility boundary

Private development tooling for the exact
`eslint-plugin-react-compiler@19.1.0-rc.2` artifact. Application, browser and SSR
schemas remain Valibot. See [ADR-048](../../../docs/adr/ADR-048-react-compiler-schema-compatibility.md)
for the owner-approved scope and review date.

## Deliberately narrow surface

This package exposes only the 15 factories used by the source-linked legacy
compiler: `array`, `boolean`, `enum`, `function`, `lazy`, `literal`, `map`,
`nativeEnum`, `nullable`, `number`, `object`, `record`, `string`, `tuple`,
and `union`. It is **not** a general Zod 3 implementation.

The engine dependency is honestly named `patched-zod: npm:zod@4.6.7`.
The alias prevents an eventual scoped legacy-consumer `zod` override from
recursively replacing this package's own engine. The loaded package must
identify itself as Zod 4.6.7; no v3 namespace is imported.

Only two compatibility bridges are introduced:

- `function().args(...)` uses the fixed engine's real function schema with an
  unknown rest schema, retaining validation, extra arguments, `this`, and
  unconstrained return values.
- A newly created map schema's `default(value)` delegates to `prefault(value)`,
  retaining legacy parsing and cloning of default maps. No global prototype
  or shared engine configuration is patched.

All other factories delegate directly to the patched engine. Invalid
configuration remains invalid; old internal error structures are not
reintroduced to imitate legacy text.

## Evidence and staged integration

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

## License

Repository-owned adapter code uses the repository's MIT license. The original
React compiler package remains unmodified and retains its upstream license;
Zod and zod-validation-error retain their own licenses and package provenance.
