import type { CssVarsThemeOptions } from "@mui/material/styles"

export const colorSchemes: CssVarsThemeOptions["colorSchemes"] = {
  light: {
    palette: {
      mode: "light",
      primary: {
        main: "#0F4FAA",
        light: "#3F7BDF",
        dark: "#123F84",
        contrastText: "#ffffff",
      },
      secondary: {
        main: "#17406F",
        contrastText: "#ffffff",
      },
      info: {
        main: "#1F68C7",
        contrastText: "#ffffff",
      },
      success: {
        main: "#2E7D32",
        contrastText: "#ffffff",
      },
      warning: {
        main: "#B7791F",
        contrastText: "#102033",
      },
      error: {
        main: "#D14343",
        contrastText: "#ffffff",
      },
      text: {
        primary: "#101621",
        secondary: "#4c5a6f",
        disabled: "rgba(59, 73, 92, 0.42)",
      },
      divider: "rgba(16, 22, 33, 0.12)",
      background: {
        default: "#e8f1fb",
        paper: "#ffffff",
      },
    },
  },
  dark: {
    palette: {
      mode: "dark",
      primary: {
        main: "#7FB6E6",
        light: "#9DC8F0",
        dark: "#2F4F75",
        contrastText: "#050B14",
      },
      secondary: {
        main: "#1B3A5D",
        contrastText: "#DDE6F7",
      },
      info: {
        main: "#8ABFEF",
        contrastText: "#050B14",
      },
      success: {
        main: "#4ADE80",
        contrastText: "#050B14",
      },
      warning: {
        main: "#FBBF24",
        contrastText: "#050B14",
      },
      error: {
        main: "#F87171",
        contrastText: "#050B14",
      },
      text: {
        primary: "#dde6f7",
        secondary: "#9fb2cc",
      },
      divider: "rgba(157, 181, 214, 0.18)",
      background: {
        default: "#060b14",
        paper: "#101a2a",
      },
    },
  },
}
