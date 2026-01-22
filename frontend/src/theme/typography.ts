import type { ThemeOptions } from "@mui/material/styles"

export const typography: NonNullable<ThemeOptions["typography"]> = {
  fontFamily: "var(--font-ui)",
  h1: {
    fontFamily: "var(--font-display)",
    fontWeight: 700,
    letterSpacing: "-0.025em",
    fontSize: "clamp(2.5rem, 5vw, 3.5rem)",
    lineHeight: 1.1,
  },
  h2: {
    fontFamily: "var(--font-display)",
    fontWeight: 600,
    letterSpacing: "-0.025em",
    fontSize: "clamp(2rem, 4vw, 2.75rem)",
    lineHeight: 1.2,
  },
  h3: {
    fontFamily: "var(--font-display)",
    fontWeight: 600,
    letterSpacing: "-0.02em",
    fontSize: "clamp(1.5rem, 3vw, 2.25rem)",
    lineHeight: 1.25,
  },
  h4: {
    fontFamily: "var(--font-display)",
    fontWeight: 600,
    letterSpacing: "-0.02em",
    fontSize: "1.5rem",
    lineHeight: 1.3,
  },
  h5: {
    fontFamily: "var(--font-display)",
    fontWeight: 600,
    letterSpacing: "-0.015em",
    fontSize: "1.25rem",
    lineHeight: 1.4,
  },
  h6: {
    fontFamily: "var(--font-display)",
    fontWeight: 600,
    letterSpacing: "-0.01em",
    fontSize: "1rem",
    lineHeight: 1.5,
  },
  body1: {
    fontSize: "1rem",
    letterSpacing: "0.01em",
    lineHeight: 1.6,
  },
  body2: {
    fontSize: "0.875rem",
    letterSpacing: "0.01em",
    lineHeight: 1.6,
  },
  subtitle1: {
    fontSize: "1rem",
    letterSpacing: "0.01em",
    lineHeight: 1.5,
    fontWeight: 500,
  },
  subtitle2: {
    fontSize: "0.875rem",
    letterSpacing: "0.01em",
    lineHeight: 1.5,
    fontWeight: 600,
  },
  button: {
    textTransform: "none",
    fontWeight: 600,
    letterSpacing: "0.02em",
  },
  caption: {
    fontSize: "0.75rem",
    letterSpacing: "0.02em",
    lineHeight: 1.5,
  },
  overline: {
    fontSize: "0.75rem",
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    lineHeight: 1.5,
    fontWeight: 700,
  },
}
