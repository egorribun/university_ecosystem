import { memo, useEffect, useState } from "react"
import { cn } from "@/utils/cn"

export const ClockWidget = memo(function ClockWidget() {
  const [time, setTime] = useState(new Date())
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    // Keep the server and hydration renders deterministic.  The browser's
    // timezone is only available after hydration, when the live clock starts.
    setMounted(true)
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div
      className={cn(
        "relative flex h-full flex-col items-center justify-center overflow-hidden rounded-3xl p-6 transition-all duration-slow",
        "border border-glass-border bg-glass-bg/(--opacity-soft) backdrop-blur-xl shadow-glass",
        "before:pointer-events-none before:absolute before:inset-0 before:bg-(--flare-primary) before:opacity-subtle"
      )}
      aria-busy={!mounted}
    >
      <div className="text-5xl font-black tracking-tighter text-text-primary sf-pro tabular-nums">
        {mounted ? (
          time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        ) : (
          <span aria-hidden="true">--:--</span>
        )}
      </div>
      <div className="mt-2 text-sm font-bold text-(--text-secondary) opacity-strong uppercase tracking-widest">
        {mounted ? (
          time.toLocaleDateString(undefined, {
            weekday: "long",
            day: "numeric",
            month: "long",
          })
        ) : (
          <span aria-hidden="true">&nbsp;</span>
        )}
      </div>
    </div>
  )
})

export default ClockWidget
