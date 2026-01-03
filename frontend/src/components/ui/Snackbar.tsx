/**
 * Snackbar Component
 *
 * A toast-like notification that appears at the bottom of the screen.
 */

import { useEffect, memo } from "react"

interface SnackbarProps {
  /** Whether the snackbar is visible */
  open: boolean
  /** Message to display */
  message: string
  /** Callback when snackbar should close */
  onClose: () => void
  /** Duration in ms before auto-close (default: 2200) */
  duration?: number
}

function Snackbar({ open, message, onClose, duration = 2200 }: SnackbarProps) {
  useEffect(() => {
    if (!open || !message) return
    const timer = setTimeout(() => {
      onClose()
    }, duration)
    return () => clearTimeout(timer)
  }, [open, message, onClose, duration])

  if (!open || !message) return null

  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in">
      <div className="rounded-2xl border border-[color:color-mix(in_srgb,white_10%,var(--nav-link)_90%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-6 py-4 text-sm font-semibold text-[color:var(--page-text)] shadow-[0_12px_32px_rgba(0,0,0,0.14),0_4px_12px_rgba(0,0,0,0.08)] backdrop-blur-xl [-webkit-backdrop-filter:blur(24px)] dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)] dark:shadow-[0_16px_40px_rgba(0,0,0,0.28),0_6px_16px_rgba(0,0,0,0.16)]">
        {message}
      </div>
    </div>
  )
}

export default memo(Snackbar)
