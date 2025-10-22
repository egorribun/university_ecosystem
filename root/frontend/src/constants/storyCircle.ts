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
  position: "relative",
  overflow: "hidden",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#fff",
  textDecoration: "none",
  border: `${borderWidth}px solid color-mix(in srgb, var(--page-text) 16%, transparent)`,
  background: "linear-gradient(135deg,#1d4ed8,#60a5fa)",
  boxShadow: "0 14px 38px rgba(37,99,235,0.18)",
  transition: "transform 0.18s ease, box-shadow 0.18s ease",
  "@media (prefers-reduced-motion: reduce)": {
    transition: "box-shadow 0.18s ease",
  },
})
