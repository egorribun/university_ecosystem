# Frontend Architecture & Standards

## Local development access

`npm run dev` and `npm run preview` use Vite's loopback-only host defaults and
default loopback-origin CORS policy. Existing proxy and service-worker headers
are unchanged.

Expose a development server to a trusted network only deliberately, for example
with `npm run dev -- --host 0.0.0.0`. The repository's `make frontend-dev` target
already selects this explicit LAN override. Do not use development or preview
servers as public production servers.

## Design System Standards

### 1. Token Usage

**NEVER** use "magic values" (arbitrary pixels or percentages) in your code.
Always use the design tokens defined in the CSS layers under `src/styles/tokens/`
and `src/styles/partials/` (mirrored in the generated `src/theme/tokens.ts`; see
[`src/styles/tokens/README.md`](src/styles/tokens/README.md)).

- **Good**: `w-(--size-icon-fluid)`
- **Bad**: `w-[22px]` or `w-[clamp(18px,4.5vw,22px)]`

If you need a new value, add it to the right token layer first, then run:

```bash
npm run tokens:sync
```

### 2. Architectural Boundaries

We enforce strict boundaries between layers using `eslint-plugin-boundaries`.

- **Components (`src/components`)**: Shared UI only. Can NOT import from `features` or `pages`.
- **Features (`src/features`)**: Business logic domains. Can NOT import from `pages`.
- **Pages (`src/pages`)**: Composition layer. Can import from anywhere.

### 3. Responsive Layouts

Use the `@utility container-fluid-responsive` for all page-level containers instead of manual `max-w-[...]` breakpoints.

```tsx
// ✅ Correct
<div className="container-fluid-responsive">...</div>
```
