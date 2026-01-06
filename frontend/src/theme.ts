import { extendTheme, responsiveFontSizes } from "@mui/material/styles";
import { colorSchemes } from "./theme/palette";
import { typography } from "./theme/typography";
import { components } from "./theme/components";
import {
  radiusScale,
  spacingScale,
  zIndexTokens,
  focusRing,
  shadows,
  glass,
} from "./theme/tokens";

const baseTheme = extendTheme({
  cssVarPrefix: "ue",
  colorSchemeSelector: "class",
  colorSchemes,
  typography,
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
  components,
});

// Inject custom tokens into the theme.vars system
const vars = baseTheme.vars as any;
vars.focusRing = focusRing;
vars.radiusScale = radiusScale;
vars.spacingScale = spacingScale;
vars.zIndexTokens = zIndexTokens;
vars.shadows = shadows;
vars.glass = glass;

const theme = responsiveFontSizes(baseTheme);

export default theme;
export type AppTheme = typeof theme;
