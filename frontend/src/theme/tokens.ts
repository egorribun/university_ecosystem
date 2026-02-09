export const spacingScale = {
  "2xs": "var(--space-1)",
  xs: "var(--space-2)",
  sm: "var(--space-3)",
  md: "var(--space-4)",
  lg: "var(--space-6)",
  xl: "var(--space-8)",
  "2xl": "var(--space-12)",
  "3xl": "var(--space-16)",
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

export const breakpoints = {
  mobile: "768px",
  tablet: "1024px",
  desktop: "1280px",
  wide: "1350px", // Standardized Navbar breakpoint
} as const

export const zIndexTokens = {
  hide: "var(--z-hide)",
  base: "var(--z-base)",
  deep: "var(--z-deep)",
  surface: "var(--z-surface)",
  sticky: "var(--z-sticky)",
  sidebar: "var(--z-sidebar)",
  navbar: "var(--z-navbar)",
  overlay: "var(--z-overlay)",
  modal: "var(--z-modal)",
  popover: "var(--z-popover)",
  floating: "var(--z-floating)",
  toast: "var(--z-toast)",
  tooltip: "var(--z-tooltip)",
} as const

export const focusRing = {
  light: "0 0 0 2px rgba(255, 255, 255, 0.9), 0 0 0 4px rgba(59, 130, 246, 0.5)",
  dark: "0 0 0 2px rgba(3, 7, 18, 0.9), 0 0 0 4px rgba(96, 165, 250, 0.6)",
} as const

export const shadows = {
  sm: "var(--shadow-1)",
  md: "var(--shadow-2)",
  lg: "var(--shadow-premium-lift)",
  xl: "0 30px 60px -12px rgba(0, 0, 0, 0.25)",
} as const

export const glass = {
  bg: "var(--glass-bg)",
  border: "var(--glass-border)",
  shadow: "var(--glass-shadow)",
  blur: "var(--glass-blur)",
  tint1: "var(--glass-tint1)",
  tint2: "var(--glass-tint2)",
  tint3: "var(--glass-tint3)",
} as const
