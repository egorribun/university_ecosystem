import { createTheme, responsiveFontSizes } from "@mui/material/styles";

const theme = responsiveFontSizes(
  createTheme({
    typography: {
      fontFamily: "var(--font-ui)",
      h1: { fontFamily: "var(--font-display)", fontWeight: 400, letterSpacing: "var(--ls-display)", fontSize: "var(--fs-h1)", lineHeight: 1.22 },
      h2: { fontFamily: "var(--font-display)", fontWeight: 400, letterSpacing: "var(--ls-display)", fontSize: "var(--fs-h2)", lineHeight: 1.22 },
      h3: { fontFamily: "var(--font-display)", fontWeight: 400, letterSpacing: "var(--ls-display)", fontSize: "var(--fs-h3)", lineHeight: 1.22 },
      h4: { fontFamily: "var(--font-display)", fontWeight: 400, letterSpacing: "var(--ls-display)", lineHeight: 1.22 },
      h5: { fontFamily: "var(--font-display)", fontWeight: 400, letterSpacing: "var(--ls-display)", lineHeight: 1.22 },
      h6: { fontFamily: "var(--font-display)", fontWeight: 400, letterSpacing: "var(--ls-display)", lineHeight: 1.22 },
      body1: { fontSize: "var(--fs-body)", letterSpacing: "var(--ls-ui)", lineHeight: 1.55 },
      body2: { fontSize: "calc(var(--fs-body) - 0.02rem)", letterSpacing: "var(--ls-ui)", lineHeight: 1.55 },
      subtitle1: { fontSize: "var(--fs-body)", letterSpacing: "var(--ls-ui)", lineHeight: 1.55, fontWeight: 500 },
      subtitle2: { fontSize: "calc(var(--fs-body) - 0.04rem)", letterSpacing: "var(--ls-ui)", lineHeight: 1.55, fontWeight: 600 },
      button: { textTransform: "none", fontWeight: 600, letterSpacing: "var(--ls-ui)" },
      caption: { fontSize: "calc(var(--fs-body) - 0.08rem)", letterSpacing: "0.01em", lineHeight: 1.4 },
      overline: { fontSize: "calc(var(--fs-body) - 0.1rem)", letterSpacing: "0.08em", textTransform: "uppercase", lineHeight: 1.4 }
    },
    components: {
      MuiButton: { styleOverrides: { root: { fontFamily: "var(--font-ui)" } } },
      MuiInputBase: { styleOverrides: { input: { fontFamily: "var(--font-ui)" } } },
      MuiInputLabel: { styleOverrides: { root: { fontFamily: "var(--font-ui)" } } },
      MuiTypography: { styleOverrides: { root: { fontFamily: "var(--font-ui)" } } },
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            fontFamily: "var(--font-ui)",
            WebkitFontSmoothing: "antialiased",
            MozOsxFontSmoothing: "grayscale",
            textRendering: "optimizeLegibility",
            fontFeatureSettings: '"tnum" 1, "lnum" 1'
          }
        }
      }
    }
  })
);

export default theme;