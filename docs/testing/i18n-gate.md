# I18N-GATE-01

`frontend/scripts/i18n-scanner.mjs` is the repository i18n contract gate. It
runs from `frontend` and checks the RU/EN product catalogues plus backend
sources that emit localized user text:

- `frontend/src/**` production TypeScript/TSX/JS source;
- `app/**/*.py` production translation call sites (including the reset/lockout
  email and Web Push notification templates);
- `app/core/localization/dictionary.py` backend RU/EN translation data.

The product scan deliberately excludes tests, stories, generated clients,
vendors, build output, Python bytecode, and coverage. The exclusion is not silent: the report
contains `scope.included`, `scope.excluded`, the excluded directory names, and
the file-name patterns. Test and generated source therefore needs its own
tests, while never becoming an implicit product-string allowlist.

## Contracts

- Every static `t(...)`/`translate(...)` key must resolve in both RU and EN.
- Every computed key must have a finite entry in
  `frontend/src/i18n/registry.ts`. Registry patterns and values may not be
  empty, non-string, or wildcard entries. A registry entry does not suppress
  catalogue parity checks for its concrete keys.
- Backend f-string and forwarding-boundary expressions use the same finite
  registry contract. The default inventory is kept in the scanner and can be
  replaced in tests with `backendDynamicRegistry`; wildcard and empty entries
  fail before source references are evaluated.
- JSX user-facing text and user-facing literal attributes must be translated;
  technical identifiers and the documented bootstrap/error-boundary literals
  are handled by narrow, source-local exceptions.
- Locale entries must have matching interpolation variables and date/number
  format specs. Plural suffix sets must match across locales, and a plural
  translation call must provide `count`.
- User-visible `Intl.DateTimeFormat`, `Intl.NumberFormat`, and
  `Intl.RelativeTimeFormat` constructors must receive an explicit locale.
- Backend email/notification `translate(...)` references and backend catalog
  entries are checked for RU/EN presence and interpolation parity.
- Language persistence is required to use the browser effect and an SSR-safe
  initializer; reading browser locale/storage during render fails the gate.

Run the focused contract tests with:

```bash
cd frontend
node --test scripts/i18n-scanner.test.mjs
npm run i18n:check
```

For CI artifacts or local diagnostics, request the stable machine-readable
shape (the default human output remains unchanged):

```bash
node scripts/i18n-scanner.mjs --json > i18n-report.json
```

The JSON report includes the aggregate errors, references, dynamic references,
scope contract, registry summary, locale summary, and backend summary. Browser
role/language journeys and hydration-warning assertions remain an E2E concern;
this scanner is a deterministic static/catalogue gate and does not replace
those tests.
