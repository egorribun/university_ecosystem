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
  "& .MuiTouchRipple-root": {
    borderRadius: "50%",
    overflow: "hidden",
  },
  "@media (prefers-reduced-motion: reduce)": {
    transition: "box-shadow 0.18s ease",
  },
})
