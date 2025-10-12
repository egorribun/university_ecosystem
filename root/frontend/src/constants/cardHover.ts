import type { SxProps } from "@mui/system"
import type { Theme } from "@mui/material/styles"

type CardHoverOptions = {
  disabled?: boolean
  hoverTransform?: string | null
  hoverBoxShadow?: string | null
  activeTransform?: string | null
}

export const cardHoverSx = ({
  disabled = false,
  hoverTransform = "scale(1.03)",
  hoverBoxShadow = "0 12px 28px rgba(0,0,0,0.18)",
  activeTransform = "scale(0.997)"
}: CardHoverOptions = {}): SxProps<Theme> => {
  const base: SxProps<Theme> = {
    transition: "transform 0.25s ease, box-shadow 0.25s ease",
    willChange: "transform",
    "@media (prefers-reduced-motion: reduce)": {
      transition: "box-shadow 0.25s ease"
    }
  }

  if (disabled) {
    return base
  }

  const hoverStyles: Record<string, unknown> = {}

  if (hoverTransform !== null && hoverTransform !== undefined) {
    hoverStyles.transform = hoverTransform
  }

  if (hoverBoxShadow !== null && hoverBoxShadow !== undefined) {
    hoverStyles.boxShadow = hoverBoxShadow
  }

  const activeStyles =
    activeTransform !== null && activeTransform !== undefined
      ? { transform: activeTransform }
      : undefined

  return {
    ...base,
    ...(Object.keys(hoverStyles).length > 0 ? { "&:hover": hoverStyles } : {}),
    ...(activeStyles ? { "&:active": activeStyles } : {})
  }
}
