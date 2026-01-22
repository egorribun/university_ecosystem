export const spacingScale = {
  "2xs": "0.25rem",
  xs: "0.5rem",
  sm: "0.75rem",
  md: "1rem",
  lg: "1.5rem",
  xl: "2rem",
  "2xl": "3rem",
  "3xl": "4.5rem",
  "4xl": "6rem",
} as const

export const radiusScale = {
  xs: "0.5rem",
  sm: "0.75rem",
  md: "1rem",
  lg: "1.5rem",
  xl: "2rem",
  "2xl": "3rem",
  pill: "9999px",
} as const

export const zIndexTokens = {
  navbar: 2600,
  overlay: 2700,
  floating: 2800,
  toast: 3400,
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
