import { type CSSProperties, type ReactNode, useEffect, useState } from "react"

type PageFadeInProps = {
  children: ReactNode
  delay?: number
  variant?: "default" | "subtle"
}

export default function PageFadeIn({ children, delay = 80, variant = "default" }: PageFadeInProps) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const frame = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div
      data-page-fade
      data-ready={ready ? "true" : "false"}
      data-variant={variant}
      style={
        {
          "--page-fade-delay": `${delay}ms`,
        } as CSSProperties
      }
      className="page-fade relative min-h-full"
    >
      {children}
    </div>
  )
}
