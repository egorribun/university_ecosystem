import React, { useEffect } from "react"
import ReactDOM from "react-dom"
import { m } from "framer-motion"
import { cn } from "@/utils/cn"
import useFocusTrap from "@/hooks/useFocusTrap"

// A11Y-65-01: Added useFocusTrap — traps Tab inside dialog, Escape calls onClose
// Wave 175 SW5: Added optional ariaLabelledBy + ariaDescribedBy for proper
// screen-reader announcements (parent supplies DialogTitle/Content IDs via
// useId() — see Profile.tsx QR + Achievement dialogs). Both props are
// OPTIONAL — existing consumers (Settings sections) continue working without
// labelledby/describedby; the dialog still has role="dialog" + aria-modal
// so the focused element identifies the modal context.
export function Dialog({
  open,
  onClose,
  maxWidth = "md",
  fullWidth = false,
  children,
  ariaLabelledBy,
  ariaDescribedBy,
}: {
  open: boolean
  onClose: () => void
  maxWidth?: string
  fullWidth?: boolean
  children: React.ReactNode
  ariaLabelledBy?: string
  ariaDescribedBy?: string
}) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => {
      document.body.style.overflow = ""
    }
  }, [open])

  const dialogRef = useFocusTrap<HTMLDivElement>({
    active: open,
    onDeactivate: onClose,
  })

  if (!open) return null

  const maxWidthClasses =
    {
      xs: "max-w-xs",
      sm: "max-w-[24rem]",
      md: "max-w-[28rem]",
      lg: "max-w-[32rem]",
      xl: "max-w-[36rem]",
    }[maxWidth] || "max-w-[28rem]"

  // Check if document is available (SSR check)
  if (typeof document === "undefined") return null

  return ReactDOM.createPortal(
    <div
      role="presentation"
      className="fixed inset-0 z-overlay flex items-center justify-center p-4"
    >
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-background/(--opacity-strong) backdrop-blur-xl"
        onClick={onClose}
      />
      <m.div
        ref={dialogRef}
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={ariaLabelledBy}
        aria-describedby={ariaDescribedBy}
        className={cn(
          "relative z-surface w-full overflow-hidden rounded-2xl border-glass-border bg-glass-bg shadow-glass backdrop-blur-glass",
          fullWidth ? "w-full" : maxWidthClasses
        )}
      >
        {children}
      </m.div>
    </div>,
    document.body
  )
}

export function DialogTitle({
  children,
  className = "",
  id,
}: {
  children: React.ReactNode
  className?: string
  // Wave 175 SW5: Optional id for aria-labelledby wiring from parent Dialog.
  id?: string
}) {
  return (
    <h2
      id={id}
      className={cn(
        "px-6 pt-6 pb-2 text-xl font-bold tracking-tight text-text-primary border-b border-(--glass-border)/(--opacity-subtle)",
        className
      )}
    >
      {children}
    </h2>
  )
}

export function DialogContent({
  children,
  className = "",
  id,
}: {
  children: React.ReactNode
  className?: string
  // Wave 175 SW5: Optional id for aria-describedby wiring from parent Dialog.
  id?: string
}) {
  return (
    <div id={id} className={cn("px-6 py-4 text-(--text-secondary) leading-relaxed", className)}>
      {children}
    </div>
  )
}

export function DialogActions({
  children,
  className = "",
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-3 border-t border-(--glass-border)/(--opacity-subtle) px-6 py-4 bg-(--bg-surface-hover)/(--opacity-dim)",
        className
      )}
    >
      {children}
    </div>
  )
}
