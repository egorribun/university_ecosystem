import { memo, useEffect, useState } from "react"
import { cn } from "@/utils/cn"

export const ClockWidget = memo(function ClockWidget() {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
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
    >
      <div className="text-5xl font-black tracking-tighter text-text-primary sf-pro tabular-nums">
        {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
      </div>
      <div className="mt-2 text-sm font-bold text-(--text-secondary) opacity-strong uppercase tracking-widest">
        {time.toLocaleDateString(undefined, {
          weekday: "long",
          day: "numeric",
          month: "long",
        })}
      </div>
    </div>
  )
})

export default ClockWidget

