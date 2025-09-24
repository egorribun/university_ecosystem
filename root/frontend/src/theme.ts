import { createTheme } from "@mui/material/styles"

type TransitionTokens = {
  fast: string
  medium: string
  slow: string
  card: string
}

type FontTokens = {
  ui: string
  display: string
}

declare module "@mui/material/styles" {
  interface Theme {
    app: {
      fonts: FontTokens
      transitions: TransitionTokens
    }
  }
  interface ThemeOptions {
    app?: {
      fonts?: Partial<FontTokens>
      transitions?: Partial<TransitionTokens>
    }
  }
}

const fontTokens: FontTokens = {
  ui: '"Oxygen","Manrope","Inter","Segoe UI",Arial,"Helvetica Neue",Helvetica,sans-serif',
  display: '"Varela","Manrope","Inter","Segoe UI",Arial,"Helvetica Neue",Helvetica,sans-serif'
}

const transitionTokens: TransitionTokens = {
  fast: "120ms cubic-bezier(.42,0,.58,1)",
  medium: "220ms cubic-bezier(.42,0,.58,1)",
  slow: "320ms cubic-bezier(.42,0,.58,1)",
  card: "420ms cubic-bezier(.22,.61,.36,1)"
}

const theme = createTheme({
  cssVariables: {
    cssVarPrefix: "ue",
    colorSchemeSelector: "data"
  },
  defaultColorScheme: "light",
  colorSchemes: {
    light: {
      palette: {
        mode: "light",
        primary: { main: "#1d5fff", contrastText: "#ffffff", light: "#65b2ff", dark: "#1a4480" },
        secondary: { main: "#0b5cad", contrastText: "#ffffff" },
        background: { default: "#f3f6fa", paper: "#ffffff" },
        text: { primary: "#10151b", secondary: "#4b5563" },
        divider: "rgba(16,21,27,0.12)",
        success: { main: "#2e7d32" },
        warning: { main: "#b7791f" },
        info: { main: "#0b5cad" }
      }
    },
    dark: {
      palette: {
        mode: "dark",
        primary: { main: "#69a9dc", contrastText: "#0b0f15", light: "#b5d4ea", dark: "#4a7aa6" },
        secondary: { main: "#7fb6e6", contrastText: "#0b0f15" },
        background: { default: "#0b0f15", paper: "#11161e" },
        text: { primary: "#e6ebf2", secondary: "#b8c2d0" },
        divider: "rgba(230,235,242,0.14)",
        success: { main: "#4ade80" },
        warning: { main: "#fbbf24" },
        info: { main: "#7fb6e6" }
      }
    }
  },
  shape: { borderRadius: 16 },
  typography: {
    fontFamily: fontTokens.ui,
    h1: { fontFamily: fontTokens.display, fontWeight: 400, letterSpacing: "0.01em", fontSize: "clamp(1.9rem, 1.2rem + 2.2vw, 3rem)", lineHeight: 1.22 },
    h2: { fontFamily: fontTokens.display, fontWeight: 400, letterSpacing: "0.01em", fontSize: "clamp(1.6rem, 1.05rem + 1.7vw, 2.4rem)", lineHeight: 1.22 },
    h3: { fontFamily: fontTokens.display, fontWeight: 400, letterSpacing: "0.01em", fontSize: "clamp(1.35rem, 0.95rem + 1.2vw, 1.9rem)", lineHeight: 1.22 },
    h4: { fontFamily: fontTokens.display, fontWeight: 400, letterSpacing: "0.01em", lineHeight: 1.22 },
    h5: { fontFamily: fontTokens.display, fontWeight: 400, letterSpacing: "0.01em", lineHeight: 1.22 },
    h6: { fontFamily: fontTokens.display, fontWeight: 400, letterSpacing: "0.01em", lineHeight: 1.22 },
    body1: { fontSize: "clamp(0.98rem, 0.94rem + 0.3vw, 1.06rem)", letterSpacing: "0.005em", lineHeight: 1.55 },
    body2: { fontSize: "calc(clamp(0.98rem, 0.94rem + 0.3vw, 1.06rem) - 0.02rem)", letterSpacing: "0.005em", lineHeight: 1.55 },
    subtitle1: { fontSize: "clamp(0.98rem, 0.94rem + 0.3vw, 1.06rem)", letterSpacing: "0.005em", lineHeight: 1.55, fontWeight: 500 },
    subtitle2: { fontSize: "calc(clamp(0.98rem, 0.94rem + 0.3vw, 1.06rem) - 0.04rem)", letterSpacing: "0.005em", lineHeight: 1.55, fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600, letterSpacing: "0.005em" },
    caption: { fontSize: "calc(clamp(0.98rem, 0.94rem + 0.3vw, 1.06rem) - 0.08rem)", letterSpacing: "0.01em", lineHeight: 1.4 },
    overline: { fontSize: "calc(clamp(0.98rem, 0.94rem + 0.3vw, 1.06rem) - 0.1rem)", letterSpacing: "0.08em", textTransform: "uppercase", lineHeight: 1.4 }
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          fontFamily: fontTokens.ui,
          borderRadius: 12,
          fontWeight: 600,
          textTransform: "none",
          letterSpacing: "0.005em",
          transition: `background ${transitionTokens.fast}, color ${transitionTokens.fast}, box-shadow ${transitionTokens.fast}`,
          boxShadow: "none",
          "&:hover": {
            boxShadow: "0 8px 24px rgba(0,0,0,0.08)"
          }
        }
      }
    },
    MuiCssBaseline: {
      styleOverrides: (themeParam) => {
        const cssTheme = themeParam as any
        const sharedVars = {
          "--font-ui": fontTokens.ui,
          "--font-display": fontTokens.display,
          "--fs-h1": "clamp(1.9rem, 1.2rem + 2.2vw, 3rem)",
          "--fs-h2": "clamp(1.6rem, 1.05rem + 1.7vw, 2.4rem)",
          "--fs-h3": "clamp(1.35rem, 0.95rem + 1.2vw, 1.9rem)",
          "--fs-body": "clamp(0.98rem, 0.94rem + 0.3vw, 1.06rem)",
          "--ls-display": "0.01em",
          "--ls-ui": "0.005em",
          "--lh-display": "1.22",
          "--lh-ui": "1.55",
          "--radius-lg": "2rem",
          "--radius-md": "1.3rem",
          "--radius-sm": "8px",
          "--shadow-1": "0 4px 32px #0001",
          "--shadow-2": "0 8px 32px #0005, 0 2px 12px #0002",
          "--shadow-focus": "0 0 0 3px rgba(0,94,162,.22), 0 0 0 6px rgba(0,94,162,.12)",
          "--glass-alpha": ".008",
          "--glass-blur": "6px",
          "--fed-blue-60v": "#005EA2",
          "--fed-blue-70v": "#1A4480",
          "--fed-blue-80v": "#0B4778",
          "--fed-blue-90v": "#112F4E",
          "--slate-05": "#F2F5F8",
          "--slate-10": "#E9EEF4",
          "--slate-20": "#D7E0E8",
          "--slate-40": "#B8C7D8",
          "--bn-h": "clamp(58px, 9.5vh, 92px)",
          "--bn-pad-v": "6px",
          "--page-bg": cssTheme.getCssVar?.("palette-background-default") ?? "var(--mui-palette-background-default)",
          "--page-text": cssTheme.getCssVar?.("palette-text-primary") ?? "var(--mui-palette-text-primary)",
          "--card-bg": cssTheme.getCssVar?.("palette-background-paper") ?? "var(--mui-palette-background-paper)",
          "--secondary-text": cssTheme.getCssVar?.("palette-text-secondary") ?? "var(--mui-palette-text-secondary)",
          "--link-color": cssTheme.getCssVar?.("palette-primary-main") ?? "var(--mui-palette-primary-main)",
          "--badge-lec": cssTheme.getCssVar?.("palette-info-main") ?? "var(--mui-palette-info-main)",
          "--badge-prac": cssTheme.getCssVar?.("palette-success-main") ?? "var(--mui-palette-success-main)",
          "--badge-lab": cssTheme.getCssVar?.("palette-warning-main") ?? "var(--mui-palette-warning-main)",
          "--progress-bar": cssTheme.getCssVar?.("palette-primary-main") ?? "var(--mui-palette-primary-main)",
          "--anim-fast": transitionTokens.fast,
          "--anim-med": transitionTokens.medium,
          "--anim-slow": transitionTokens.slow,
          "--anim-card": transitionTokens.card
        }

        const lightVars = {
          "--nav-bg": "#f5f6f7",
          "--nav-text": "#10151b",
          "--nav-link": "#005ea2",
          "--nav-link-hover": "#1a4480",
          "--btn-bg": "#f7f9fb",
          "--btn-border": "#d4d8de",
          "--table-header-bg": "#e9eef4",
          "--table-row-hover": "#eff3f8",
          "--table-row-today": "#e2eaf4",
          "--menu-hover-bg": "#e8f0fa",
          "--menu-hover-text": "#0f2a47",
          "--option-bg": "#ffffff",
          "--option-hover-bg": "#f2f7fc",
          "--option-shadow": "0 2px 14px #c7d1de70",
          "--selection-bg": "#d7e7f6",
          "--selection-text": "#0e141b",
          "--hero-grad-start": "#eaf1f8",
          "--hero-grad-end": "#d9e6f4",
          "--progress-track": "#e2e7ee",
          "--glass-bg": "rgba(255,255,255,.012)",
          "--glass-border": "rgba(255,255,255,.18)",
          "--glass-shadow": "inset 0 0 0 1px rgba(0,0,0,.02), 0 18px 50px rgba(0,0,0,.14)",
          "--glass-highlight": "rgba(255,255,255,.5)",
          "--glass-tint-1": "rgba(255,255,255,.06)",
          "--glass-tint-2": "rgba(255,255,255,.02)",
          "--glass-tint-3": "rgba(255,255,255,.01)",
          "--hint-fg": "rgba(0,0,0,.6)",
          "--placeholder-fg": "rgba(0,0,0,.45)"
        }

        const darkVars = {
          "--nav-bg": "#0e1116",
          "--nav-text": "#e6ebf2",
          "--nav-link": "#69a9dc",
          "--nav-link-hover": "#b5d4ea",
          "--btn-bg": "#11161e",
          "--btn-border": "#263142",
          "--table-header-bg": "#121923",
          "--table-row-hover": "#152031",
          "--table-row-today": "#17243a",
          "--menu-hover-bg": "#121923",
          "--menu-hover-text": "#b5d4ea",
          "--option-bg": "#11161e",
          "--option-hover-bg": "#152031",
          "--option-shadow": "0 3px 16px #0a111999",
          "--selection-bg": "#1c2735",
          "--selection-text": "#e6ebf2",
          "--hero-grad-start": "#0b1220",
          "--hero-grad-end": "#0b0f15",
          "--progress-track": "#1c2735",
          "--glass-bg": "rgba(8,12,18,.06)",
          "--glass-border": "rgba(255,255,255,.10)",
          "--glass-shadow": "inset 0 0 0 1px rgba(255,255,255,.02), 0 22px 60px rgba(0,0,0,.36)",
          "--glass-highlight": "rgba(255,255,255,.18)",
          "--glass-tint-1": "rgba(255,255,255,.05)",
          "--glass-tint-2": "rgba(255,255,255,.02)",
          "--glass-tint-3": "rgba(255,255,255,.01)",
          "--hint-fg": "rgba(255,255,255,.72)",
          "--placeholder-fg": "rgba(255,255,255,.64)"
        }

        const darkSelector = cssTheme.getColorSchemeSelector?.("dark") ?? '[data-color-scheme="dark"]'

        return {
          ":root": {
            ...sharedVars,
            ...lightVars
          },
          [darkSelector]: {
            ...sharedVars,
            ...darkVars
          },
          "html": {
            minHeight: "100%",
            scrollBehavior: "smooth"
          },
          "body": {
            minHeight: "100vh",
            backgroundColor: "var(--page-bg)",
            color: "var(--page-text)",
            fontFamily: fontTokens.ui,
            fontWeight: 400,
            lineHeight: "var(--lh-ui)",
            letterSpacing: "var(--ls-ui)",
            WebkitFontSmoothing: "antialiased",
            MozOsxFontSmoothing: "grayscale",
            textRendering: "optimizeLegibility",
            transition: `background-color ${transitionTokens.medium}, color ${transitionTokens.medium}`
          },
          "#root": {
            minHeight: "100dvh"
          },
          "::selection": {
            backgroundColor: "var(--selection-bg)",
            color: "var(--selection-text)"
          },
          "::-moz-selection": {
            backgroundColor: "var(--selection-bg)",
            color: "var(--selection-text)"
          },
          "*, *::before, *::after": {
            boxSizing: "border-box"
          }
        }
      }
    }
  },
  app: {
    fonts: fontTokens,
    transitions: transitionTokens
  }
})

export default theme
