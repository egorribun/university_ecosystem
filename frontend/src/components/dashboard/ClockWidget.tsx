import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

export function ClockWidget() {
  const { t } = useTranslation()
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div
      className={cn(
        "relative flex h-full flex-col items-center justify-center overflow-hidden rounded-3xl p-6 transition-all duration-500",
        "border border-glass-border bg-glass-bg/30 backdrop-blur-xl shadow-glass",
        "before:pointer-events-none before:absolute before:inset-0 before:bg-(--flare-primary) before:opacity-10"
      )}
    >
      <div className="text-5xl font-black tracking-tighter text-(--text-primary) sf-pro tabular-nums">
        {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
      </div>
      <div className="mt-2 text-sm font-bold text-(--text-secondary) opacity-60 uppercase tracking-widest">
        {time.toLocaleDateString(undefined, {
          weekday: "long",
          day: "numeric",
          month: "long",
        })}
      </div>
    </div>
  )
}
