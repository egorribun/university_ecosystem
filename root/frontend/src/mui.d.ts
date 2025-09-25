import type theme from "./theme";

declare module "@mui/material/styles" {
  interface ThemeVars {
    focusRing: typeof theme.vars.focusRing;
    radiusScale: typeof theme.vars.radiusScale;
    spacingScale: typeof theme.vars.spacingScale;
    zIndexTokens: typeof theme.vars.zIndexTokens;
  }
}
