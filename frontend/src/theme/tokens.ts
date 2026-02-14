// -----------------------------------------------------------------------------
// TOKENS.TS
// -----------------------------------------------------------------------------
// This file is a strict TypeScript mirror of the CSS variables defined in
// `src/styles/theme.css`. It is used for JS-based styling (e.g., Framer Motion).
//
// ⚠️  WARNING: DO NOT EDIT VALUES HERE MANUALLY.
//     Always update `src/styles/theme.css` first, then run `npm run tokens:sync`.
// -----------------------------------------------------------------------------

export const spacingScale = {
  "05": "var(--space-05)",
  "10": "var(--space-10)",
  "125": "var(--space-125)",
  "15": "var(--space-15)",
  "20": "var(--space-20)",
  "24": "var(--space-24)",
  "25": "var(--space-25)",
  "2xl": "var(--space-12)",
  "2xs": "var(--space-1)",
  "35": "var(--space-35)",
  "3xl": "var(--space-16)",
  "4xl": "var(--space-32)",
  "5": "var(--space-5)",
  "9": "var(--space-9)",
  lg: "var(--space-6)",
  md: "var(--space-4)",
  sm: "var(--space-3)",
  xl: "var(--space-8)",
  xs: "var(--space-2)",
} as const

export const radiusScale = {
  "2xl": "var(--radius-2xl)",
  "3xl": "var(--radius-3xl)",
  lg: "var(--radius-lg)",
  md: "var(--radius-md)",
  pill: "var(--radius-full)",
  sm: "var(--radius-sm)",
  xl: "var(--radius-xl)",
  xs: "var(--radius-xs)",
} as const

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
  base: "var(--z-base)",
  content: "var(--z-content)",
  decor: "var(--z-decor)",
  deep: "var(--z-deep)",
  dropdown: "var(--z-dropdown)",
  floating: "var(--z-floating)",
  hide: "var(--z-hide)",
  modal: "var(--z-modal)",
  navbar: "var(--z-navbar)",
  negative: "var(--z-negative)",
  offline: "var(--z-offline)",
  overlay: "var(--z-overlay)",
  popover: "var(--z-popover)",
  sidebar: "var(--z-sidebar)",
  sticky: "var(--z-sticky)",
  surface: "var(--z-surface)",
  toast: "var(--z-toast)",
  tooltip: "var(--z-tooltip)",
} as const

export const focusRing = {
  default: "var(--shadow-focus)",
} as const

export const shadows = {
  glass: "var(--shadow-glass)",
  lg: "var(--shadow-premium-lift)",
  md: "var(--shadow-md)",
  sm: "var(--shadow-sm)",
} as const

export const glass = {
  bg: "var(--glass-bg)",
  border: "var(--glass-border)",
  tint3: "var(--glass-tint3)",
} as const

export const fluidTypography = {
  display: "var(--fs-fluid-display)",
  h1: "var(--fs-fluid-h1)",
  h2: "var(--fs-fluid-h2)",
  h3: "var(--fs-fluid-h3)",
} as const

export const dimensions = {
  avatarXl: "var(--size-avatar-xl)",
  cardMd: "var(--w-card-md)",
  cardSm: "var(--w-card-sm)",
  heroLg: "var(--h-hero-lg)",
  heroMax: "var(--h-hero-max-portrait)",
  heroMax: "var(--h-hero-max-square)",
  heroMax: "var(--h-hero-max-landscape)",
  heroMd: "var(--h-hero-md)",
  heroSm: "var(--h-hero-sm)",
  screenOffset: "var(--h-screen-offset)",
} as const

export const opacity = {
  heavy: "var(--opacity-heavy)",
  hover: "var(--opacity-hover)",
  medium: "var(--opacity-medium)",
  soft: "var(--opacity-soft)",
  strong: "var(--opacity-strong)",
} as const

export const scale = {
  active: "0.98",
  hover: "var(--scale-hover)",
} as const

export const motion = {
  staggerDelay: 0.06,
  durationFast: 0.2,
  durationMedium: 0.45,
  navTransition: 1.2,
} as const

