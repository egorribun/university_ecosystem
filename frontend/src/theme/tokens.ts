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
  "1": "var(--space-1)",
  "10": "var(--space-10)",
  "11": "var(--space-11)",
  "12": "var(--space-12)",
  "125": "var(--space-125)",
  "15": "var(--space-15)",
  "16": "var(--space-16)",
  "2": "var(--space-2)",
  "20": "var(--space-20)",
  "24": "var(--space-24)",
  "25": "var(--space-25)",
  "2xl": "var(--space-12)",
  "2xs": "var(--space-1)",
  "3": "var(--space-3)",
  "32": "var(--space-32)",
  "35": "var(--space-35)",
  "36": "var(--space-36)",
  "3xl": "var(--space-16)",
  "4": "var(--space-4)",
  "40": "var(--space-40)",
  "48": "var(--space-48)",
  "4xl": "var(--space-32)",
  "5": "var(--space-5)",
  "52": "var(--space-52)",
  "56": "var(--space-56)",
  "6": "var(--space-6)",
  "64": "var(--space-64)",
  "8": "var(--space-8)",
  "80": "var(--space-80)",
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
  "4xl": "var(--radius-4xl)",
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
  storiesInHero: "1220px",
  desktop: "1280px",
  wide: "1350px",
  ultrawide: "1730px",
} as const

export const zIndexTokens = {
  base: "var(--z-base)",
  content: "var(--z-content)",
  decor: "var(--z-decor)",
  deep: "var(--z-deep)",
  dialog: "var(--z-dialog)",
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
  default: "var(--focus-ring-default)",
  isolated: "var(--focus-ring-isolated)",
  thick: "var(--focus-ring-thick)",
} as const

export const shadows = {
  glass: "var(--shadow-glass)",
} as const

export const glass = {
  bg: "var(--glass-bg)",
  blur: "var(--glass-blur)",
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
  heroMax: "var(--h-hero-max)",
  heroMaxLandscape: "var(--h-hero-max-landscape)",
  heroMaxPortrait: "var(--h-hero-max-portrait)",
  heroMaxSquare: "var(--h-hero-max-square)",
  heroMd: "var(--h-hero-md)",
  heroSm: "var(--h-hero-sm)",
  screenOffset: "var(--h-screen-offset)",
} as const

export const opacity = {
  dim: "var(--opacity-dim)",
  faint: "var(--opacity-faint)",
  heavy: "var(--opacity-heavy)",
  hover: "var(--opacity-hover)",
  low: "var(--opacity-low)",
  medium: "var(--opacity-medium)",
  micro: "var(--opacity-micro)",
  soft: "var(--opacity-soft)",
  strong: "var(--opacity-strong)",
  subtle: "var(--opacity-subtle)",
  whisper: "var(--opacity-whisper)",
} as const

export const scale = {
  active: "0.98",
  hover: "var(--scale-hover)",
} as const

export const motion = {
  delayBase: 0.15,
  delayLong: 0.2,
  delayNone: 0,
  delayShort: 0.1,
  durationAura: 14,
  durationBase: 0.3,
  durationDefault: 0.35,
  durationFast: 0.2,
  durationHero: 1.2,
  durationInstant: 0.1,
  durationLazy: 0.9,
  durationMedium: 0.45,
  durationPulse: 1.8,
  durationPulseSlow: 2,
  durationRapid: 0.15,
  durationShimmer: 1.6,
  durationSlow: 0.5,
  durationSlower: 0.7,
  durationTyping: 1.4,
  navTransition: 1.2,
  scaleIn: "0.95",
  scaleOut: "1.05",
  slideLg: "50px",
  slideMd: "20px",
  slideSm: "10px",
  staggerDelay: 0.08,
} as const

export const icon = {
  sm: "var(--size-icon-sm)",
} as const

export const letterSpacing = {
  body: "var(--tracking-body)",
} as const
