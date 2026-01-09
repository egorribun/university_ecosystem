import type { Components, Theme } from "@mui/material/styles"
import { spacingScale, radiusScale, focusRing, zIndexTokens } from "./tokens"

export const components: Components<Theme> = {
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
        const radiusVars = (theme as any).vars?.radiusScale ?? radiusScale
        const focusVars = (theme as any).vars?.focusRing ?? focusRing

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
        const radiusVars = (theme as any).vars?.radiusScale ?? radiusScale
        const spacingVars = (theme as any).vars?.spacingScale ?? spacingScale

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
        const radiusVars = (theme as any).vars?.radiusScale ?? radiusScale
        const spacingVars = (theme as any).vars?.spacingScale ?? spacingScale
        const focusVars = (theme as any).vars?.focusRing ?? focusRing

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
        const radiusVars = (theme as any).vars?.radiusScale ?? radiusScale
        const spacingVars = (theme as any).vars?.spacingScale ?? spacingScale
        const focusVars = (theme as any).vars?.focusRing ?? focusRing

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
        const radiusVars = (theme as any).vars?.radiusScale ?? radiusScale
        const focusVars = (theme as any).vars?.focusRing ?? focusRing

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
        const radiusVars = (theme as any).vars?.radiusScale ?? radiusScale
        const focusVars = (theme as any).vars?.focusRing ?? focusRing

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
}
