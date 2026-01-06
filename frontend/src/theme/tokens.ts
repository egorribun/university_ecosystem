export const spacingScale = {
  "2xs": "0.25rem",
  xs: "0.5rem",
  sm: "0.75rem",
  md: "1rem",
  lg: "1.5rem",
  xl: "2rem",
  "2xl": "3rem",
} as const;

export const radiusScale = {
  xs: "0.35rem",
  sm: "0.5rem",
  md: "0.75rem",
  lg: "1rem",
  xl: "1.75rem",
  pill: "999px",
} as const;

export const zIndexTokens = {
  navbar: 2600,
  overlay: 2700,
  floating: 2800,
  toast: 3400,
} as const;

export const focusRing = {
  light:
    "0 0 0 1px rgba(255, 255, 255, 0.92), 0 0 0 4px rgba(var(--mui-palette-primary-mainChannel) / 0.35)",
  dark: "0 0 0 1px rgba(11, 15, 21, 0.92), 0 0 0 4px rgba(var(--mui-palette-primary-mainChannel) / 0.5)",
} as const;

export const shadows = {
  sm: "var(--shadow-1)",
  md: "var(--shadow-2)",
  lg: "var(--dash-panel-shadow)",
  xl: "var(--dash-panel-hover-shadow)",
} as const;

export const glass = {
  bg: "var(--glass-bg)",
  border: "var(--glass-border)",
  shadow: "var(--glass-shadow)",
  blur: "var(--glass-blur)",
} as const;
