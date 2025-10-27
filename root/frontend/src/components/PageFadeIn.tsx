import { type CSSProperties, type ReactNode, useEffect, useState } from "react"

type PageFadeInProps = {
  children: ReactNode
  delay?: number
}

export default function PageFadeIn({ children, delay = 80 }: PageFadeInProps) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const frame = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div
      data-page-fade
      data-ready={ready ? "true" : "false"}
      style={
        {
          "--page-fade-delay": `${delay}ms`,
          transitionDelay: `${delay}ms`,
          willChange: "opacity, transform",
        } as CSSProperties
      }
      className="relative min-h-full translate-y-[18px] opacity-0 transition-[opacity,transform] duration-[560ms] ease-[cubic-bezier(0.33,1,0.68,1)] motion-reduce:translate-y-0 motion-reduce:opacity-100 motion-reduce:transition-none data-[ready=true]:translate-y-0 data-[ready=true]:opacity-100"
    >
      {children}
    </div>
  )
}
