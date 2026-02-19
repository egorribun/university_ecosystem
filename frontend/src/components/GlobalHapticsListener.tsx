import { useEffect } from "react"
import { useHaptics, type HapticStyle } from "@/hooks/useHaptics"

export function GlobalHapticsListener() {
  const { trigger } = useHaptics()

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      const hapticElement = target.closest("[data-haptic]") as HTMLElement

      if (hapticElement) {
        // Prevent double triggering if nested
        // logic could be added here, but closest() usually handles the most specific one
        const style = hapticElement.dataset.haptic as HapticStyle
        trigger(style)
      }
    }

    // Use capture phase to ensure we catch it even if propagation is stopped?
    // No, standard bubbling is usually fine, but if a button stops propagation, we might miss it.
    // Let's use capture = true to be safe, or just standard bubbling.
    // Actually, if a button stops propagation, it might be for a reason.
    // But haptics are usually desired. Let's stick to bubbling first.
    document.addEventListener("click", handleClick)

    return () => {
      document.removeEventListener("click", handleClick)
    }
  }, [trigger])

  return null
}
