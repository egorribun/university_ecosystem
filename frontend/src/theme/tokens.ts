// -----------------------------------------------------------------------------
// TOKENS.TS
// -----------------------------------------------------------------------------
// This file is a strict TypeScript mirror of the CSS variables defined in
// `src/styles/theme.css`. It is used for JS-based styling (e.g., Framer Motion).
//
// ⚠️  WARNING: DO NOT EDIT VALUES HERE MANUALLY.
//     Always update `src/styles/theme.css` first, then reflect the change here.
// -----------------------------------------------------------------------------

export const spacingScale = {
  "2xs": "var(--space-1)", // 0.25rem
  xs: "var(--space-2)", // 0.5rem
  sm: "var(--space-3)", // 0.75rem
  md: "var(--space-4)", // 1rem
  lg: "var(--space-6)", // 1.5rem
  xl: "var(--space-8)", // 2rem
  "2xl": "var(--space-12)", // 3rem
  "3xl": "var(--space-16)", // 4rem
  "4xl": "var(--space-32)", // 8rem (Updated to match theme.css --space-32)
} as const

export const radiusScale = {
  xs: "var(--radius-xs)",
  sm: "var(--radius-sm)",
  md: "var(--radius-md)",
  lg: "var(--radius-lg)",
  xl: "var(--radius-xl)",
  "2xl": "var(--radius-2xl)",
  pill: "var(--radius-full)",
} as const

// Breakpoints should match Tailwind config and CSS variables
export const breakpoints = {
  small: "640px",
  mobile: "768px",
  content: "900px",
  tablet: "1024px",
  dashboard: "1100px",
  desktop: "1280px",
  wide: "1350px",
  ultrawide: "1730px",
} as const

export const zIndexTokens = {
  hide: "var(--z-hide)",
  base: "var(--z-base)",
  decor: "var(--z-decor)",
  deep: "var(--z-deep)",
  surface: "var(--z-surface)",
  content: "var(--z-content)",
  sticky: "var(--z-sticky)",
  sidebar: "var(--z-sidebar)",
  navbar: "var(--z-navbar)",
  overlay: "var(--z-overlay)",
  modal: "var(--z-modal)",
  dropdown: "var(--z-dropdown)",
  popover: "var(--z-popover)",
  floating: "var(--z-floating)",
  toast: "var(--z-toast)",
  tooltip: "var(--z-tooltip)",
} as const

export const focusRing = {
  default: "var(--shadow-focus)",
} as const

export const shadows = {
  sm: "var(--shadow-sm)",
  md: "var(--shadow-md)",
  lg: "var(--shadow-premium-lift)",
  glass: "var(--shadow-glass)",
} as const

export const glass = {
  bg: "var(--glass-bg)",
  border: "var(--glass-border)",
  shadow: "var(--glass-shadow)",
  blur: "var(--glass-blur)",
  tint3: "var(--glass-tint3)",
} as const

export const fluidTypography = {
  display: "var(--fs-fluid-display)",
  h1: "var(--fs-fluid-h1)",
  h2: "var(--fs-fluid-h2)",
  h3: "var(--fs-fluid-h3)",
} as const

export const dimensions = {
  heroLg: "var(--h-hero-lg)",
  heroMd: "var(--h-hero-md)",
  heroSm: "var(--h-hero-sm)",
  screenOffset: "var(--h-screen-offset)",
  avatarXl: "var(--size-avatar-xl)",
  cardSm: "var(--w-card-sm)",
  cardMd: "var(--w-card-md)",
} as const

export const opacity = {
  faint: "var(--opacity-faint)",
  subtle: "var(--opacity-subtle)",
  dim: "var(--opacity-dim)",
  soft: "var(--opacity-soft)",
  medium: "var(--opacity-medium)",
  strong: "var(--opacity-strong)",
  hover: "var(--opacity-hover)",
  heavy: "var(--opacity-heavy)",
} as const

/**
 * Scale tokens for interactive states.
 * - `hover`: Standard hover enlargement (matches `--scale-hover`).
 * - `active`: Standard press-down reduction.
 */
export const scale = {
  hover: "var(--scale-hover)",
  active: "0.98",
} as const

/**
 * Shared motion constants for Framer Motion variants.
 * Centralizing these ensures consistent animation timing across the app.
 */
export const motion = {
  staggerDelay: 0.06,
  durationFast: 0.2,
  durationMedium: 0.45,
  navTransition: 1.2,
} as const
