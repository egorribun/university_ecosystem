import { Box } from "@mui/material"
import { type ReactNode, useEffect, useState } from "react"

type PageFadeInProps = {
  children: ReactNode
  delay?: number
}

const transitionEase = "cubic-bezier(0.33, 1, 0.68, 1)"

export default function PageFadeIn({ children, delay = 80 }: PageFadeInProps) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const frame = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <Box
      data-ready={ready ? "true" : "false"}
      sx={{
        position: "relative",
        minHeight: "100%",
        opacity: ready ? 1 : 0,
        transform: ready ? "none" : "translateY(18px)",
        transition: `opacity 560ms ${transitionEase} ${delay}ms, transform 560ms ${transitionEase} ${delay}ms`,
        willChange: "opacity, transform",
        "& [data-fade]": {
          opacity: ready ? 1 : 0,
          transform: ready ? "none" : "translateY(22px)",
          transitionProperty: "opacity, transform",
          transitionDuration: "560ms",
          transitionTimingFunction: transitionEase,
          transitionDelay: `calc(var(--fade-delay, 120ms) + ${delay}ms)`,
          willChange: "opacity, transform",
        },
        "@media (prefers-reduced-motion: reduce)": {
          opacity: 1,
          transform: "none",
          transition: "none",
          "& [data-fade]": {
            opacity: 1,
            transform: "none",
            transition: "none",
          },
        },
      }}
    >
      {children}
    </Box>
  )
}
