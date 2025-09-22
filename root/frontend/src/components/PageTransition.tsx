import { FC, ReactNode, useEffect } from "react"
import { LazyMotion, domAnimation, m, useReducedMotion } from "framer-motion"

type Props = { children: ReactNode }

let didPaint = false

const PageTransition: FC<Props> = ({ children }) => {
  const prefersReduced = useReducedMotion()
  const initial = didPaint ? { opacity: 0.001, y: 12 } : false

  useEffect(() => {
    didPaint = true
  }, [])

  if (prefersReduced) return <>{children}</>

  return (
    <LazyMotion features={domAnimation}>
      <div style={{ position: "relative", minHeight: "100%", background: "var(--page-bg)" }}>
        <m.div
          initial={initial}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.2, ease: [0.2, 0, 0, 1] } }}
          exit={{ opacity: 0.001, y: -10, transition: { duration: 0.16, ease: [0.4, 0, 0.2, 1] } }}
          style={{ position: "relative", zIndex: 1, willChange: "transform, opacity", backfaceVisibility: "hidden", transform: "translateZ(0)" }}
        >
          {children}
        </m.div>
      </div>
    </LazyMotion>
  )
}

export default PageTransition