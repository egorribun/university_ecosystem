import { Suspense, lazy, type ComponentProps } from "react"

type AnimatePresenceProps = ComponentProps<typeof import("framer-motion").AnimatePresence>

const LazyAnimatePresence = lazy(() =>
  import("framer-motion").then((mod) => ({ default: mod.AnimatePresence }))
)

export default function MotionPresence({ children, ...props }: AnimatePresenceProps) {
  return (
    <Suspense fallback={<>{children}</>}>
      <LazyAnimatePresence initial={false} mode="wait" {...props}>
        {children}
      </LazyAnimatePresence>
    </Suspense>
  )
}
