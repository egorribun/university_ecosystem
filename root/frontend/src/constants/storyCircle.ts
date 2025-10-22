import type { SxProps } from "@mui/material/styles"
import type { Theme } from "@mui/material"

type StoryCircleOptions = {
  size?: number
  borderWidth?: number
}

export const storyCircleSx = ({
  size = 76,
  borderWidth = 2,
}: StoryCircleOptions = {}): SxProps<Theme> => ({
  width: size,
  height: size,
  minWidth: size,
  minHeight: size,
  borderRadius: "50%",
  overflow: "visible",
  position: "relative",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#fff",
  textDecoration: "none",
  border: `${borderWidth}px solid color-mix(in srgb, var(--page-text) 16%, transparent)`,
  background: "linear-gradient(135deg,#1d4ed8,#60a5fa)",
  boxShadow: "0 10px 28px rgba(37,99,235,0.18)",
  transition: "box-shadow 0.18s ease",
  "&::after": {
    content: "''",
    position: "absolute",
    inset: 0,
    borderRadius: "inherit",
    boxShadow:
      "0 0 0 3px rgba(125,172,255,0.46), 0 0 0 6px rgba(37,99,235,0.14), 0 18px 48px rgba(37,99,235,0.32)",
    outline: "2px solid rgba(125,172,255,0.32)",
    outlineOffset: 6,
    opacity: 0,
    transform: "scale(0.94)",
    transition: "opacity 0.2s ease, transform 0.2s ease",
    pointerEvents: "none",
  },
  "& .MuiTouchRipple-root": {
    borderRadius: "50%",
    overflow: "hidden",
  },
  "& .MuiTouchRipple-root, & .MuiTouchRipple-ripple, & .MuiTouchRipple-child": {
    borderRadius: "50%",
  },
  "@media (prefers-reduced-motion: reduce)": {
    transition: "box-shadow 0.18s ease",
  },
})
