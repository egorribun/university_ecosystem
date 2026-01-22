import type { CssVarsThemeOptions } from "@mui/material/styles"

export const colorSchemes: CssVarsThemeOptions["colorSchemes"] = {
  light: {
    palette: {
      mode: "light",
      primary: {
        main: "#3b82f6", // Electric Blue
        light: "#60a5fa",
        dark: "#2563eb",
        contrastText: "#ffffff",
      },
      secondary: {
        main: "#475569", // Slate
        light: "#64748b",
        dark: "#334155",
        contrastText: "#ffffff",
      },
      info: {
        main: "#0ea5e9", // Sky
        contrastText: "#ffffff",
      },
      success: {
        main: "#22c55e", // Green
        contrastText: "#ffffff",
      },
      warning: {
        main: "#f59e0b", // Amber
        contrastText: "#ffffff",
      },
      error: {
        main: "#ef4444", // Red
        contrastText: "#ffffff",
      },
      text: {
        primary: "#1e293b", // Slate 800
        secondary: "#475569", // Slate 600
        disabled: "#94a3b8", // Slate 400
      },
      divider: "rgba(148, 163, 184, 0.12)",
      background: {
        default: "#f0f4f8",
        paper: "#ffffff",
      },
    },
  },
  dark: {
    palette: {
      mode: "dark",
      primary: {
        main: "#60a5fa", // Blue 400 (Brighter for Dark Mode)
        light: "#93c5fd",
        dark: "#3b82f6",
        contrastText: "#030712",
      },
      secondary: {
        main: "#94a3b8", // Slate 400
        light: "#cbd5e1",
        dark: "#64748b",
        contrastText: "#030712",
      },
      info: {
        main: "#38bdf8", // Sky 400
        contrastText: "#030712",
      },
      success: {
        main: "#4ade80", // Green 400
        contrastText: "#030712",
      },
      warning: {
        main: "#fbbf24", // Amber 400
        contrastText: "#030712",
      },
      error: {
        main: "#f87171", // Red 400
        contrastText: "#030712",
      },
      text: {
        primary: "#f8fafc", // Slate 50
        secondary: "#94a3b8", // Slate 400
      },
      divider: "rgba(148, 163, 184, 0.1)",
      background: {
        default: "#030712", // Midnight
        paper: "#0f172a", // Slate 900
      },
    },
  },
}
