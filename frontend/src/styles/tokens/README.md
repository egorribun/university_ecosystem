# Design Tokens

This directory holds the project's design tokens. Tokens are CSS custom
properties (`--*`) imported via `tailwind.css` into `@layer base`, available
to every component, every Tailwind utility, and exported to TypeScript via
`scripts/sync-tokens.mjs` for JS consumers (Framer Motion, computed styles).

## Layered Structure

The token system has three layers, each with a clear responsibility:

```
primitives.css     — raw values: color scales, blurs, opacities, motion timings
       │             (no semantic intent; just numeric constants)
       ▼
semantics.css      — semantic mappings: --bg-page, --text-primary, --color-brand,
       │             --raw-shadow-focus, category badge palette (cat-*)
       │             (theme-aware: :root for light, .dark for dark overrides)
       ▼
scoped tokens      — feature-page tokens scoped to .{events,news,schedule,...}-theme
                     (events.css, news.css, schedule.css, activity.css, map.css,
                      dashboard.css, components.css)
```

The complementary `../partials/` directory holds primitives that aren't
semantic mappings but cross-cut layers — `_glass-layers.css` for frosted
glass surfaces, `_modern-css.css` for `@property` registrations and
modern-CSS utilities, `_micro-interactions.css` for hover/focus animations.

## Override Pattern (intentional, NOT drift)

Some tokens are **deliberately redefined** in scoped contexts to give a
themed page bigger typography, custom orbs, or distinct accent colors. The
canonical example:

```css
/* primitives.css → semantic baseline */
:root {
  --fs-card-title: 1rem;
  --fs-hero: 2rem;
}

/* dashboard.css → bigger typography on .dashboard-theme */
.dashboard-theme {
  --fs-card-title: 1.125rem; /* INTENTIONAL */
  --fs-hero: 3rem; /* INTENTIONAL */
}
```

Wave 120 SW6 audit confirmed this is **intentional design**, not token drift.
A scoped override does NOT mean the global value is wrong — it means the
scoped context has a different design language.

If you find a duplicated token across scoped files (same name, same value
in two `.{events,news,…}-theme` blocks) without a semantic difference,
that **IS** drift — consolidate to `semantics.css`. Wave 121 SW4 did
exactly this for the `--cat-{color}-{bg|text}` palette (was duplicated
identically across `events.css` + `news.css`, now lives in
`semantics.css :root` + `.dark`).

## Focus Rings

The canonical box-shadow focus-ring primitive is:

```css
/* primitives.css */
--focus-ring-default: 0 0 0 2px var(--color-brand);
--focus-ring-thick: 0 0 0 3px var(--color-brand);
--focus-ring-isolated: var(--raw-shadow-focus); /* WCAG-AA double-ring */
```

Use `--focus-ring-default` for most cases. Use `--focus-ring-thick` when
the visual demands more emphasis (large buttons, hero CTAs). Use
`--focus-ring-isolated` for elements rendered on **colored backgrounds**
where the solid brand color alone would have insufficient contrast — the
double-ring (2px bg-page + 4px primary-main) provides a WCAG-AA compliant
focus indicator regardless of the underlying background.

These tokens are **CSS-only primitives**. Use them via `box-shadow`,
including the `inset` variant:

```css
.my-button:focus-visible {
  box-shadow: var(--focus-ring-default);
}

.my-cell:focus-visible {
  outline: none;
  box-shadow:
    inset var(--focus-ring-default),
    inset 0 0 8px var(--brand-glow);
}
```

**Don't use these tokens for:**

- decorative borders (use `border:` or composed `box-shadow: 0 0 0 1px ...`)
- animation pulse keyframes (variable-radius growing rings)
- avatar rings, drag indicators, hover/active state rings (separate semantics)

The Map page intentionally uses `outline: 2px solid var(--color-brand)`
for `:focus-visible` instead of box-shadow — `outline` doesn't trigger
layout effects on absolutely-positioned MapLibre markers, while box-shadow
can interact with `transform` and stacking contexts. Both are WCAG-compliant.

## Naming Conventions

Tokens follow `--{category}-{prop}-{variant}`:

| Token                      | Category | Prop     | Variant |
| -------------------------- | -------- | -------- | ------- |
| `--color-blue-500`         | color    | blue     | 500     |
| `--bg-page`                | bg       | page     | (none)  |
| `--text-primary`           | text     | primary  | (none)  |
| `--cat-emerald-bg`         | cat      | emerald  | bg      |
| `--focus-ring-default`     | focus    | ring     | default |
| `--motion-duration-medium` | motion   | duration | medium  |

Some legacy categories exist (e.g. `--fs-*` for font-size, `--space-*`
for spacing, `--radius-*` for radii, `--ease-*` for easing curves).
Don't introduce a new prefix without checking the existing inventory
first — search via `grep -rE '^\s*--(prefix-)' src/styles/`.

## Sync Workflow

`tokens.ts` is **auto-generated** from CSS by `scripts/sync-tokens.mjs`.
Don't edit `src/theme/tokens.ts` directly — your changes will be wiped
on the next `npm run build`.

The sync script:

1. Reads ALL CSS variables in `partials/` + `tokens/` (regex-based)
2. Categorizes them into TS export groups (colors, motion, fontSize,
   focusRing, shadows, glass, etc.) by name pattern
3. Writes typed `as const` exports to `src/theme/tokens.ts`

To add a new token:

1. Add `--my-new-token: value;` to the appropriate CSS file
2. Run `npm run tokens:sync`
3. If the new token should be JS-accessible, verify it appears in `tokens.ts`
   under the right group. If it doesn't, update the GROUPS array in
   `scripts/sync-tokens.mjs` (add a pattern that matches your token).
4. Commit both the CSS change AND the regenerated `tokens.ts`.

CI gates the sync via `npm run tokens:sync && git diff --exit-code`. If
this fails, somebody's CSS source got out of sync with `tokens.ts` —
re-run the sync and commit the result.

## Wave-by-Wave Token Changes

The audit trail in `docs/audits/INDEX.md` documents per-wave
token additions, removals, and consolidations. Notable entries:

- **Wave 120 SW6**: removed 3 orphan `@property` registrations + 12
  hardcoded radii → `--radius-{xs,sm}` token references (628 vars)
- **Wave 121 SW4**: consolidated `--cat-*` category palette from
  `events.css` + `news.css` to `semantics.css` (no count change — same
  names, just relocated)
- **Wave 121 SW5**: added 3 `--focus-ring-*` primitives (631 vars).
  Audit revealed only 1 box-shadow focus-ring site needed tokenization;
  others are decorative borders, animations, or use `outline:` instead.
