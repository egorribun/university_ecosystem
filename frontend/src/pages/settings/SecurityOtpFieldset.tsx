import { useRef, type FocusEvent, type ReactNode } from "react"
import { useIsomorphicLayoutEffect } from "@/hooks/useIsomorphicLayoutEffect"

interface SecurityOtpFieldsetProps {
  identityPending: boolean
  children: ReactNode
}

export function SecurityOtpFieldset({ identityPending, children }: SecurityOtpFieldsetProps) {
  const lastFocusedInput = useRef<HTMLInputElement | null>(null)
  const fieldsetRef = useRef<HTMLFieldSetElement | null>(null)
  const wasPending = useRef(false)

  useIsomorphicLayoutEffect(() => {
    const focused = document.activeElement
    if (focused instanceof HTMLInputElement && fieldsetRef.current?.contains(focused)) {
      lastFocusedInput.current = focused
    }
  }, [])

  useIsomorphicLayoutEffect(() => {
    if (identityPending) {
      wasPending.current = true
      if (!lastFocusedInput.current) return
      const forgetFocus = () => {
        lastFocusedInput.current = null
      }
      document.addEventListener("focusin", forgetFocus)
      document.addEventListener("pointerdown", forgetFocus)
      document.addEventListener("keydown", forgetFocus)
      return () => {
        document.removeEventListener("focusin", forgetFocus)
        document.removeEventListener("pointerdown", forgetFocus)
        document.removeEventListener("keydown", forgetFocus)
      }
    }

    if (!wasPending.current) return
    wasPending.current = false
    const input = lastFocusedInput.current
    lastFocusedInput.current = null
    if (
      input?.isConnected &&
      document.activeElement === document.body &&
      document.hasFocus() &&
      !input.matches(":disabled")
    ) {
      input.focus()
    }
  }, [identityPending])

  const handleFocus = (event: FocusEvent<HTMLFieldSetElement>) => {
    if (event.target instanceof HTMLInputElement) lastFocusedInput.current = event.target
  }

  const handleBlur = (event: FocusEvent<HTMLFieldSetElement>) => {
    const fieldset = event.currentTarget
    const target: EventTarget = event.target
    // Disabling a fieldset blurs its focused input. Keep it only for that
    // transition; ordinary navigation away must not be undone later.
    queueMicrotask(() => {
      if (
        !fieldset.disabled &&
        target instanceof HTMLInputElement &&
        lastFocusedInput.current === target
      ) {
        lastFocusedInput.current = null
      }
    })
  }

  return (
    <fieldset
      ref={fieldsetRef}
      disabled={identityPending}
      onFocusCapture={handleFocus}
      onBlurCapture={handleBlur}
      className="min-w-0 border-0 p-0"
    >
      {children}
    </fieldset>
  )
}
