# Frontend Architecture & Standards

## Design System Standards

### 1. Token Usage

**NEVER** use "magic values" (arbitrary pixels or percentages) in your code.
Always use the Design Tokens defined in `src/styles/theme.css` and mirrored in `src/theme/tokens.ts`.

- **Good**: `w-(--size-icon-fluid)`
- **Bad**: `w-[22px]` or `w-[clamp(18px,4.5vw,22px)]`

If you need a new value, add it to `theme.css` first, then run:

```bash
npm run tokens:sync
```

### 2. Architectural Boundaries

We enforce strict strict boundaries between layers using `eslint-plugin-boundaries`.

- **Components (`src/components`)**: Shared UI only. Can NOT import from `features` or `pages`.
- **Features (`src/features`)**: Business logic domains. Can NOT import from `pages`.
- **Pages (`src/pages`)**: Composition layer. Can import from anywhere.

### 3. Responsive Layouts

Use the `@utility container-fluid-responsive` for all page-level containers instead of manual `max-w-[...]` breakpoints.

```tsx
// ✅ Correct
<div className="container-fluid-responsive">...</div>
```
