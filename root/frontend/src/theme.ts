import { extendTheme, responsiveFontSizes } from "@mui/material/styles"

const spacingScale = {
  "2xs": "0.25rem",
  xs: "0.5rem",
  sm: "0.75rem",
  md: "1rem",
  lg: "1.5rem",
  xl: "2rem",
  "2xl": "3rem",
} as const

const radiusScale = {
  xs: "0.35rem",
  sm: "0.5rem",
  md: "0.75rem",
  lg: "1rem",
  xl: "1.75rem",
  pill: "999px",
} as const

const zIndexTokens = {
  navbar: 2600,
  overlay: 2700,
  floating: 2800,
  toast: 3400,
} as const

const focusRing = {
  light:
    "0 0 0 1px rgba(255, 255, 255, 0.92), 0 0 0 4px rgba(var(--mui-palette-primary-mainChannel) / 0.35)",
  dark: "0 0 0 1px rgba(11, 15, 21, 0.92), 0 0 0 4px rgba(var(--mui-palette-primary-mainChannel) / 0.5)",
} as const

const shadows = {
  sm: "var(--shadow-1)",
  md: "var(--shadow-2)",
  lg: "var(--dash-panel-shadow)",
  xl: "var(--dash-panel-hover-shadow)",
} as const

const glass = {
  bg: "var(--glass-bg)",
  border: "var(--glass-border)",
  shadow: "var(--glass-shadow)",
  blur: "var(--glass-blur)",
} as const

const baseTheme = extendTheme({
  cssVarPrefix: "ue",
  colorSchemeSelector: "class",
  colorSchemes: {
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
          secondary: "#3B495C",
          disabled: "rgba(59, 73, 92, 0.42)",
        },
        divider: "rgba(16, 22, 33, 0.12)",
        background: {
          default: "#E8F1FB",
          paper: "#FFFFFF",
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
          primary: "#DDE6F7",
          secondary: "#9FB2CC",
        },
        divider: "rgba(157, 181, 214, 0.18)",
        background: {
          default: "#060B14",
          paper: "#101A2A",
        },
      },
    },
  },
  typography: {
    fontFamily: "var(--font-ui)",
    h1: {
      fontFamily: "var(--font-display)",
      fontWeight: 400,
      letterSpacing: "var(--ls-display)",
      fontSize: "var(--fs-h1)",
      lineHeight: 1.22,
    },
    h2: {
      fontFamily: "var(--font-display)",
      fontWeight: 400,
      letterSpacing: "var(--ls-display)",
      fontSize: "var(--fs-h2)",
      lineHeight: 1.22,
    },
    h3: {
      fontFamily: "var(--font-display)",
      fontWeight: 400,
      letterSpacing: "var(--ls-display)",
      fontSize: "var(--fs-h3)",
      lineHeight: 1.22,
    },
    h4: {
      fontFamily: "var(--font-display)",
      fontWeight: 400,
      letterSpacing: "var(--ls-display)",
      lineHeight: 1.22,
    },
    h5: {
      fontFamily: "var(--font-display)",
      fontWeight: 400,
      letterSpacing: "var(--ls-display)",
      lineHeight: 1.22,
    },
    h6: {
      fontFamily: "var(--font-display)",
      fontWeight: 400,
      letterSpacing: "var(--ls-display)",
      lineHeight: 1.22,
    },
    body1: {
      fontSize: "var(--fs-body)",
      letterSpacing: "var(--ls-ui)",
      lineHeight: 1.55,
    },
    body2: {
      fontSize: "calc(var(--fs-body) - 0.02rem)",
      letterSpacing: "var(--ls-ui)",
      lineHeight: 1.55,
    },
    subtitle1: {
      fontSize: "var(--fs-body)",
      letterSpacing: "var(--ls-ui)",
      lineHeight: 1.55,
      fontWeight: 500,
    },
    subtitle2: {
      fontSize: "calc(var(--fs-body) - 0.04rem)",
      letterSpacing: "var(--ls-ui)",
      lineHeight: 1.55,
      fontWeight: 600,
    },
    button: {
      textTransform: "none",
      fontWeight: 600,
      letterSpacing: "var(--ls-ui)",
    },
    caption: {
      fontSize: "calc(var(--fs-body) - 0.08rem)",
      letterSpacing: "0.01em",
      lineHeight: 1.4,
    },
    overline: {
      fontSize: "calc(var(--fs-body) - 0.1rem)",
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      lineHeight: 1.4,
    },
  },
  shape: {
    borderRadius: 12,
  },
  spacing: 4,
  zIndex: {
    appBar: zIndexTokens.navbar,
    drawer: zIndexTokens.overlay,
    modal: zIndexTokens.floating,
    snackbar: zIndexTokens.toast,
    tooltip: zIndexTokens.toast + 100,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        ":root": {
          "--ue-spacing-2xs": spacingScale["2xs"],
          "--ue-spacing-xs": spacingScale.xs,
          "--ue-spacing-sm": spacingScale.sm,
          "--ue-spacing-md": spacingScale.md,
          "--ue-spacing-lg": spacingScale.lg,
          "--ue-spacing-xl": spacingScale.xl,
          "--ue-spacing-2xl": spacingScale["2xl"],
          "--ue-radius-xs": radiusScale.xs,
          "--ue-radius-sm": radiusScale.sm,
          "--ue-radius-md": radiusScale.md,
          "--ue-radius-lg": radiusScale.lg,
          "--ue-radius-xl": radiusScale.xl,
          "--ue-radius-pill": radiusScale.pill,
          "--ue-focus-ring": focusRing.light,
          "--ue-z-index-nav": `${zIndexTokens.navbar}`,
          "--ue-z-index-overlay": `${zIndexTokens.overlay}`,
          "--ue-z-index-floating": `${zIndexTokens.floating}`,
          "--ue-z-index-toast": `${zIndexTokens.toast}`,
        },
        ":root[data-mui-color-scheme='dark']": {
          "--ue-focus-ring": focusRing.dark,
        },
        html: {
          scrollBehavior: "smooth",
        },
        body: {
          fontFamily: "var(--font-ui)",
          WebkitFontSmoothing: "antialiased",
          MozOsxFontSmoothing: "grayscale",
          textRendering: "optimizeLegibility",
          fontFeatureSettings: '"tnum" 1, "lnum" 1',
        },
        "*:focus-visible": {
          outline: "none",
        },
        "@media (prefers-reduced-motion: reduce)": {
          html: {
            scrollBehavior: "auto",
          },
          "*, *::before, *::after": {
            animationDuration: "0.001ms !important",
            animationIterationCount: "1 !important",
            transitionDuration: "0.001ms !important",
            transitionDelay: "0ms !important",
          },
        },
      },
    },
    MuiButtonBase: {
      styleOverrides: {
        root: ({ theme }) => {
          const radiusVars = theme.vars?.radiusScale ?? radiusScale
          const focusVars = theme.vars?.focusRing ?? focusRing

          return {
            minHeight: "44px",
            minWidth: "44px",
            borderRadius: `max(${radiusVars.md}, 0.75rem)`,
            transition: "background-color 0.18s ease, box-shadow 0.2s ease, transform 0.18s ease",
            outline: "none",
            "&:focus-visible": {
              outline: "none",
              boxShadow: `var(--ue-focus-ring, ${focusVars.light})`,
            },
          }
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: ({ theme }) => {
          const radiusVars = theme.vars?.radiusScale ?? radiusScale
          const spacingVars = theme.vars?.spacingScale ?? spacingScale

          return {
            borderRadius: radiusVars.lg,
            paddingInline: `max(${spacingVars.sm}, ${theme.spacing(2)})`,
            paddingBlock: `max(${spacingVars["2xs"]}, ${theme.spacing(1)})`,
            minHeight: "44px",
          }
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: ({ theme }) => {
          const radiusVars = theme.vars?.radiusScale ?? radiusScale
          const spacingVars = theme.vars?.spacingScale ?? spacingScale
          const focusVars = theme.vars?.focusRing ?? focusRing

          return {
            minWidth: "44px",
            minHeight: "44px",
            borderRadius: radiusVars.pill,
            padding: spacingVars.xs,
            "&:focus-visible": {
              boxShadow: `var(--ue-focus-ring, ${focusVars.light})`,
            },
          }
        },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: ({ theme }) => {
          const radiusVars = theme.vars?.radiusScale ?? radiusScale
          const spacingVars = theme.vars?.spacingScale ?? spacingScale
          const focusVars = theme.vars?.focusRing ?? focusRing

          return {
            minHeight: "44px",
            borderRadius: radiusVars.md,
            paddingInline: spacingVars.sm,
            "&:focus-visible": {
              boxShadow: `var(--ue-focus-ring, ${focusVars.light})`,
            },
          }
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: ({ theme }) => {
          const radiusVars = theme.vars?.radiusScale ?? radiusScale
          const focusVars = theme.vars?.focusRing ?? focusRing

          return {
            minHeight: "48px",
            borderRadius: radiusVars.md,
            "&:focus-visible": {
              boxShadow: `var(--ue-focus-ring, ${focusVars.light})`,
            },
          }
        },
      },
    },
    MuiLink: {
      styleOverrides: {
        root: ({ theme }) => {
          const radiusVars = theme.vars?.radiusScale ?? radiusScale
          const focusVars = theme.vars?.focusRing ?? focusRing

          return {
            borderRadius: radiusVars.sm,
            outline: "none",
            "&:focus-visible": {
              outline: "none",
              boxShadow: `var(--ue-focus-ring, ${focusVars.light})`,
            },
          }
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: "var(--ue-radius-lg)",
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: "var(--ue-radius-lg)",
        },
      },
    },
  },
})

const vars = baseTheme.vars as any
vars.focusRing = focusRing
vars.radiusScale = radiusScale
vars.spacingScale = spacingScale
vars.zIndexTokens = zIndexTokens
vars.shadows = shadows
vars.glass = glass

const theme = responsiveFontSizes(baseTheme)

export default theme

export type AppTheme = typeof theme
