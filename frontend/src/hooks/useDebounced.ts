import { useEffect, useState } from "react"

// PERF-23-04 (audit 2026-03-25 Wave 23): Strategy-based delay presets.
// "search" (200ms)     — fast response for search-as-you-type UX
// "validation" (350ms) — avoids expensive server-side validation on every keystroke
// "default" (300ms)    — balanced general-purpose debounce
const DELAY_PRESETS = {
  search: 200,
  default: 300,
  validation: 350,
} as const

type DelayPreset = keyof typeof DELAY_PRESETS

/**
 * Debounces a value by the given delay or strategy preset.
 *
 * @example
 * const dSearch = useDebounced(search, "search")   // 200ms — fast for search-as-you-type
 * const dEmail = useDebounced(email, "validation")  // 350ms — waits for typing pause
 * const dValue = useDebounced(value, 500)            // custom ms
 */
export function useDebounced<T>(value: T, delay: number | DelayPreset = "default") {
  const ms = typeof delay === "number" ? delay : DELAY_PRESETS[delay]
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return v
}
