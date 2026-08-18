/**
 * FlipCountdown — Flip-clock style MM:SS countdown.
 * Shows when next lesson starts in < 30 minutes.
 * CSS 3D card-flip on digit change. Wave 66 (Idea #13).
 */
import { useState, useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

interface FlipCountdownProps {
  /** Target time in minutes since midnight */
  targetMinutes: number
  /** Called when countdown reaches zero */
  onComplete?: () => void
  className?: string
}

function padTwo(n: number): string {
  return n < 10 ? `0${n}` : `${n}`
}

function FlipDigit({ value, label }: { value: string; label: string }) {
  const [current, setCurrent] = useState(value)
  const [previous, setPrevious] = useState(value)
  const [flipping, setFlipping] = useState(false)
  const currentRef = useRef(value)

  useEffect(() => {
    if (value !== currentRef.current) {
      setPrevious(currentRef.current)
      setCurrent(value)
      currentRef.current = value
      setFlipping(true)
      // Duration synced with CSS --sched-flip-duration (FIX-69-03)
      const FLIP_DURATION_MS = 500
      const timer = setTimeout(() => setFlipping(false), FLIP_DURATION_MS)
      return () => clearTimeout(timer)
    }
  }, [value])

  return (
    <div className="sched-flip-digit-group" aria-label={`${value} ${label}`}>
      <div className={cn("sched-flip-digit", flipping && "sched-flip-active")}>
        {/* Static top half — shows current value */}
        <div className="sched-flip-top">
          <span>{current}</span>
        </div>
        {/* Static bottom half — shows current value */}
        <div className="sched-flip-bottom">
          <span>{current}</span>
        </div>
        {/* Animated top flap — flips down from previous to current */}
        {flipping && (
          <div className="sched-flip-top-flap">
            <span>{previous}</span>
          </div>
        )}
        {/* Animated bottom flap — reveals current value */}
        {flipping && (
          <div className="sched-flip-bottom-flap">
            <span>{current}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export function FlipCountdown({ targetMinutes, onComplete, className }: FlipCountdownProps) {
  const { t } = useTranslation(["schedule"])
  const [secondsLeft, setSecondsLeft] = useState(() => {
    const now = new Date()
    const nowSecs = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()
    return Math.max(0, targetMinutes * 60 - nowSecs)
  })
  const onCompleteRef = useRef(onComplete)
  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  /* FIX-67-06: setInterval(1000) replaces rAF — countdown only needs 1fps.
     Pauses when tab hidden (Page Visibility API) to save battery. */
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "hidden") return
      setSecondsLeft((prev) => {
        const next = Math.max(0, prev - 1)
        if (next === 0) onCompleteRef.current?.()
        return next
      })
    }, 1000)
    return () => clearInterval(id)
  }, [targetMinutes])

  const mins = Math.floor(secondsLeft / 60)
  const secs = secondsLeft % 60
  const minStr = padTwo(mins)
  const secStr = padTwo(secs)
  const isUrgent = secondsLeft > 0 && secondsLeft <= 300 // Last 5 minutes (FIX-68-17)

  return (
    <div
      className={cn("sched-flip-countdown inline-flex items-center gap-1", className)}
      role="timer"
      aria-live="polite"
      aria-label={t("schedule:countdown.ariaLabel", { mins, secs })}
      data-urgent={isUrgent || undefined}
    >
      <FlipDigit value={minStr[0]!} label={t("schedule:countdown.tensOfMinutes")} />
      <FlipDigit value={minStr[1]!} label={t("schedule:countdown.unitMinutes")} />
      <span className="sched-flip-colon">:</span>
      <FlipDigit value={secStr[0]!} label={t("schedule:countdown.tensOfSeconds")} />
      <FlipDigit value={secStr[1]!} label={t("schedule:countdown.unitSeconds")} />
    </div>
  )
}
