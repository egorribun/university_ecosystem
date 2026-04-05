/**
 * FlipCountdown — Flip-clock style MM:SS countdown.
 * Shows when next lesson starts in < 30 minutes.
 * CSS 3D card-flip on digit change. Wave 66 (Idea #13).
 */
import { useState, useEffect, useRef } from "react"
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

  useEffect(() => {
    if (value !== current) {
      setPrevious(current)
      setCurrent(value)
      setFlipping(true)
      const timer = setTimeout(() => setFlipping(false), 500)
      return () => clearTimeout(timer)
    }
  }, [value, current])

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

export function FlipCountdown({
  targetMinutes,
  onComplete,
  className,
}: FlipCountdownProps) {
  const [secondsLeft, setSecondsLeft] = useState(() => {
    const now = new Date()
    const nowSecs = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()
    return Math.max(0, targetMinutes * 60 - nowSecs)
  })
  const rafRef = useRef<number>(0)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    let lastTick = performance.now()
    const tick = (now: number) => {
      // Update every ~1 second
      if (now - lastTick >= 1000) {
        lastTick = now
        setSecondsLeft((prev) => {
          const next = Math.max(0, prev - 1)
          if (next === 0) onCompleteRef.current?.()
          return next
        })
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [targetMinutes])

  const mins = Math.floor(secondsLeft / 60)
  const secs = secondsLeft % 60
  const minStr = padTwo(mins)
  const secStr = padTwo(secs)

  return (
    <div
      className={cn("sched-flip-countdown inline-flex items-center gap-1", className)}
      role="timer"
      aria-live="polite"
      aria-label={`${mins} минут ${secs} секунд`}
    >
      <FlipDigit value={minStr[0]} label="десятки минут" />
      <FlipDigit value={minStr[1]} label="минуты" />
      <span className="sched-flip-colon">:</span>
      <FlipDigit value={secStr[0]} label="десятки секунд" />
      <FlipDigit value={secStr[1]} label="секунды" />
    </div>
  )
}
