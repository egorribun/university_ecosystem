import { useCallback } from "react"

export type HapticStyle = "light" | "medium" | "heavy" | "success" | "warning" | "error"

export function useHaptics() {
  const trigger = useCallback((style: HapticStyle = "light") => {
    if (typeof navigator === "undefined" || !navigator.vibrate) return

    switch (style) {
      case "light":
        navigator.vibrate(10)
        break
      case "medium":
        navigator.vibrate(20)
        break
      case "heavy":
        navigator.vibrate(40)
        break
      case "success":
        navigator.vibrate([10, 50, 10])
        break
      case "warning":
        navigator.vibrate([30, 100, 30])
        break
      case "error":
        navigator.vibrate([50, 50, 50, 50, 50])
        break
    }
  }, [])

  return { trigger }
}
