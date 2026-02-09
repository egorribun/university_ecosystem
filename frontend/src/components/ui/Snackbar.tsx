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
    <div className="fixed bottom-24 left-1/2 z-toast -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in">
      <div className="flex items-center gap-2 rounded-ue-lg border border-glass-border-subtle bg-glass-elevated px-5 py-3 text-sm font-black uppercase tracking-widest text-primary-text shadow-premium backdrop-blur-2xl [-webkit-backdrop-filter:blur(24px)]">
        {message}
      </div>
    </div>
  )
}

export default memo(Snackbar)
