/**
 * Snackbar Component
 *
 * A toast-like notification that appears at the bottom of the screen.
 */

import { memo, useEffect } from "react"

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

const DEFAULT_DURATION = 2200

function Snackbar({ open, message, onClose, duration = DEFAULT_DURATION }: SnackbarProps) {
  useEffect(() => {
    if (!open || !message) return
    const timer = setTimeout(() => {
      onClose()
    }, duration)
    return () => clearTimeout(timer)
  }, [open, message, onClose, duration])

  if (!open || !message) return null

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="fixed bottom-24 left-1/2 z-toast -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in"
    >
      <div className="glass-layer-floating flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-black uppercase tracking-widest text-text-primary">
        {message}
      </div>
    </div>
  )
}

export default memo(Snackbar)
