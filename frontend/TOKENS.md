# Token System Documentation

## Overview

The Design System uses a centralized token architecture where `src/styles/theme.css` acts as the **source of truth**. All values are defined as standard CSS variables and synchronized to TypeScript for JavaScript-based usage.

## Architecture

### Source of Truth

- **File**: `src/styles/theme.css`
- **Format**: Standard CSS Custom Properties (Variables)
- **Role**: Defines all colors, spacing, typography, motion, and layout constants.

### Consumption

1. **CSS/Tailwind**: Use CSS variables directly (e.g., `var(--color-primary)`, `w-(--spacing-4)`).
2. **TypeScript/React**: Use `src/theme/tokens.ts` (e.g., `tokens.spacing.md`, `tokens.colors.primary`).

### Synchronization

To ensure type safety and consistency, a script generates `tokens.ts` from `theme.css`.

```bash
npm run tokens:sync
```

**Always run this command after modifying `theme.css`.**

## Token Categories

### Colors `(--color-*)`

- **Base**: `slate`, `white`, `black`
- **Brand**: `blue-600` (Primary), `sky-400` (Dark Primary)
- **Status**: `success` (green), `warning` (amber), `error` (red)
- **Semantic**: `bg-page`, `text-primary`, `border-subtle`

### Spacing `(--space-*)`

- Scale: `05` (0.125rem) to `80` (20rem)
- Mapped to `tokens.spacingScale` (e.g., `--space-4` -> `tokens.spacingScale.md`)

### Typography `(--fs-*)`

- **Fluid**: `h1`, `h2`, `body` (using `clamp()`)
- **Fixed**: `sm`, `base`, `lg`, `xl`

### Layout `(--layout-*)`

- Max widths for containers: `page`, `content`, `wide`, `ultrawide`

### Letter Spacing `(--tracking-*)`

- `widest-xl`: `0.25em` (Primary for micro-labels)
- `hero`: `0.3em` (Specialized for hero section branding)

### Shadows & Effects `(--shadow-*, --glass-*)`

- Premium shadows with mixed opacity.
- **Pulse Shadows**: Deprecated in favor of Tailwind `ring` utilities (`ring-brand/15`) for better consistency with the spacing scale.
- Glassmorphism tokens for blur and transparency.

### Motion `(--motion-*)`

- **Durations**: `fast` (0.2s), `base` (0.3s), `medium` (0.45s), `slow` (0.5s), `lazy` (0.9s).
- **Usage**: Always use the `motion` export from `@/theme/tokens` for `framer-motion` components to ensure synchronization with CSS.

## Best Practices

1. **Never hardcode values**. Use tokens.
2. **Favor semantic tokens** (`bg-surface`) over raw colors (`slate-50`).
3. **Use Tailwind Ring** for status glows instead of custom `box-shadow` styles.
4. **Clean up**: If a token is deprecated, remove it from `theme.css` and run sync.
