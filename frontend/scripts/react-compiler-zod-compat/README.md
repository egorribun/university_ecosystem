# React Compiler schema compatibility boundary

`@university-ecosystem/react-compiler-zod-compat@1.0.0` is repository-owned,
MIT-licensed development tooling for the exact
`eslint-plugin-react-compiler@19.1.0-rc.2` consumer. Its `private: true`
manifest flag prevents npm publication; it does not make this public
repository or an archive private.

This facade must not be imported by application, browser, SSR or
production-runtime code. Application validation remains subject to the
repository's Valibot policy. This usage restriction is not a claim that the
whole dependency graph is Zod-free.

## Deliberately narrow surface

The CommonJS entrypoint exports `{ z }`. The frozen `z` object exposes only
these 15 factories used by the source-linked legacy compiler: `array`,
`boolean`, `enum`, `function`, `lazy`, `literal`, `map`, `nativeEnum`,
`nullable`, `number`, `object`, `record`, `string`, `tuple` and `union`.
It is **not** a general Zod 3 implementation.

The engine dependency is honestly named `patched-zod: npm:zod@4.6.7`.
The alias prevents a scoped legacy-consumer `zod` override from recursively
replacing this package's own engine. The loaded package must identify itself
as Zod 4.6.7; no v3 namespace is imported.

Only two compatibility bridges are introduced:

- `function().args(...)` uses the fixed engine's real function schema with an
  unknown rest schema, retaining validation, extra arguments, `this`, and
  unconstrained return values.
- A newly created map schema's `default(value)` delegates to `prefault(value)`,
  retaining legacy parsing and cloning of default maps. No global prototype
  or shared engine configuration is patched.

All other factories delegate directly to the patched engine. Invalid
configuration remains invalid; old internal error structures are not
reintroduced to imitate legacy text. This package does not expand the
compiler's existing defaults, diagnostics, severity or suppression guarantees.

## Package boundary

The package payload consists of exactly `package.json`, `index.cjs`,
`LICENSE` and `README.md`. It contains no compiler bundle, legacy baseline,
test fixtures or lifecycle scripts. The original React compiler artifact is
not vendored or rewritten by this package.

Repository policy, phase-specific dependency layout, source-bound test
evidence and acceptance status are maintained outside this package in
`docs/adr/ADR-048-react-compiler-schema-compatibility.md` and
`docs/testing/react-compiler-facade-integration.md`. Packaging alone is not
dependency, compatibility or vulnerability acceptance.

## License

Repository-owned adapter code uses the repository's MIT license. The original
React compiler package remains unmodified and retains its upstream license;
Zod and zod-validation-error retain their own licenses and package provenance.
