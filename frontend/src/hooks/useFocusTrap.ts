import { useEffect, useRef } from "react"
import type { FocusTrap, Options as FocusTrapOptions } from "focus-trap"
import { createFocusTrap } from "focus-trap"

type InitialFocusTarget = FocusTrapOptions["initialFocus"]
type FallbackFocusTarget = FocusTrapOptions["fallbackFocus"]

export interface UseFocusTrapOptions {
  /** Whether the focus trap should be active. */
  active: boolean
  /** Callback invoked when the underlying trap deactivates. */
  onDeactivate?: () => void
  /** Element focused when the trap activates. */
  initialFocus?: InitialFocusTarget
  /** Fallback target if no focusable element is found. */
  fallbackFocus?: FallbackFocusTarget
  /** Allow clicks outside of the trap without deactivating it. */
  allowOutsideClick?: boolean
  /** Whether focus should return to the previously focused element. */
  returnFocus?: boolean
  /** Whether Escape should deactivate the trap. */
  escapeDeactivates?: boolean
}

export default function useFocusTrap<T extends HTMLElement>({
  active,
  onDeactivate,
  initialFocus,
  fallbackFocus,
  allowOutsideClick = true,
  returnFocus = true,
  escapeDeactivates = true,
}: UseFocusTrapOptions) {
  const containerRef = useRef<T | null>(null)
  const trapRef = useRef<FocusTrap | null>(null)
  const deactivateRef = useRef(onDeactivate)
  const skipDeactivateRef = useRef(false)
  const initialFocusRef = useRef<InitialFocusTarget | undefined>(initialFocus)

  useEffect(() => {
    deactivateRef.current = onDeactivate
    initialFocusRef.current = initialFocus
  }, [onDeactivate, initialFocus])

  useEffect(() => {
    const container = containerRef.current
    if (!container || !active) {
      return undefined
    }

    const fallbackTarget: FallbackFocusTarget =
      typeof fallbackFocus !== "undefined"
        ? fallbackFocus
        : ((() => {
            if (container.tabIndex < 0) container.tabIndex = -1
            return container
          }) as FallbackFocusTarget)

    const options: FocusTrapOptions = {
      allowOutsideClick,
      escapeDeactivates,
      returnFocusOnDeactivate: returnFocus,
      fallbackFocus: fallbackTarget,
    }

    // `!== undefined` (not truthy) — supports `initialFocus: false` to prevent auto-focus
    if (initialFocusRef.current !== undefined) options.initialFocus = initialFocusRef.current

    const trap = createFocusTrap(container, {
      ...options,
      onDeactivate: () => {
        if (skipDeactivateRef.current) return
        deactivateRef.current?.()
      },
    })

    trap.activate()
    trapRef.current = trap

    return () => {
      skipDeactivateRef.current = true
      trap.deactivate()
      skipDeactivateRef.current = false
      trapRef.current = null
    }
  }, [active, allowOutsideClick, escapeDeactivates, fallbackFocus, returnFocus])

  return containerRef
}
