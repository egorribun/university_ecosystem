import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react"
import { createPortal } from "react-dom"
import useFocusTrap, { type UseFocusTrapOptions } from "@/hooks/useFocusTrap"
import { X } from "lucide-react"
import { cn } from "@/utils/cn"

type DialogSize = "sm" | "md" | "lg"

const sizeClassMap: Record<DialogSize, string> = {
  sm: "sm:max-w-[24rem]",
  md: "sm:max-w-[32rem]",
  lg: "sm:max-w-[42rem]",
}

export type DialogProps = {
  open: boolean
  onClose: () => void
  title?: ReactNode
  subtitle?: ReactNode
  children: ReactNode
  footer?: ReactNode
  /** Defaults to `md`. */
  size?: DialogSize
  /** When true, the dialog takes the full screen height on narrow viewports. */
  fullScreenOnMobile?: boolean
  className?: string
  bodyClassName?: string
  footerClassName?: string
  closeLabel?: string
  initialFocus?: UseFocusTrapOptions["initialFocus"]
}

export function Dialog({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = "md",
  fullScreenOnMobile = false,
  className,
  bodyClassName,
  footerClassName,
  closeLabel = "Close",
  initialFocus,
}: DialogProps) {
  const [portalNode, setPortalNode] = useState<HTMLElement | null>(null)
  const [mounted, setMounted] = useState(false)
  const dialogTitleId = useId()
  const dialogSubtitleId = useId()
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    const node = document.createElement("div")
    node.dataset.dialogRoot = "true"
    document.body.appendChild(node)
    setPortalNode(node)
    setMounted(true)
    return () => {
      document.body.removeChild(node)
      setPortalNode(null)
      setMounted(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  const dialogRef = useFocusTrap<HTMLDivElement>({
    active: open,
    onDeactivate: onClose,
    // The callback is only invoked for an open, committed dialog, whose close
    // button is always present in the same portal subtree.
    initialFocus: initialFocus ?? (() => closeButtonRef.current!),
    allowOutsideClick: true,
  })

  const labelledBy = useMemo(() => {
    if (!title) return undefined
    return dialogTitleId
  }, [dialogTitleId, title])

  const describedBy = useMemo(() => {
    if (!subtitle) return undefined
    return dialogSubtitleId
  }, [dialogSubtitleId, subtitle])

  if (!mounted || !portalNode || !open) {
    return null
  }

  return createPortal(
    <div
      className="fixed inset-0 z-overlay flex items-center justify-center overflow-y-auto px-fluid-x py-fluid-y"
      role="presentation"
    >
      <div
        className="absolute inset-0 bg-overlay-bg backdrop-blur-overlay"
        aria-hidden="true"
        onClick={onClose}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        className={cn(
          "relative z-surface w-full max-w-(--dialog-max-w)",
          sizeClassMap[size],
          fullScreenOnMobile
            ? "h-dvh max-h-dvh overflow-y-auto rounded-none bg-(--bg-surface) pb-6 pt-5 text-(--text-primary) shadow-surface-strong ring-1 ring-white/(--opacity-subtle) sm:h-auto sm:rounded-2xl sm:px-6 sm:pb-7"
            : "glass-layer-elevated overflow-y-auto rounded-2xl pb-6 pt-5 text-(--text-primary) ring-1 ring-white/(--opacity-subtle) sm:px-6 sm:pb-7",
          "focus:outline-none",
          className
        )}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            {title ? (
              <h2 id={dialogTitleId} className="text-detail-title font-semibold text-text-primary">
                {title}
              </h2>
            ) : null}
            {subtitle ? (
              <p id={dialogSubtitleId} className="text-sm font-medium text-(--text-secondary)">
                {subtitle}
              </p>
            ) : null}
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/(--opacity-subtle) bg-(--glass-bg)/(--opacity-hover) text-(--primary-main) shadow-surface transition hover:bg-(--glass-bg) focus-ring-premium"
          >
            <span className="sr-only">{closeLabel}</span>
            <X className="h-4 w-4 text-(--primary-main)" aria-hidden />
          </button>
        </div>
        <div className={cn("mt-5 space-y-5", bodyClassName)}>{children}</div>
        {footer ? (
          <div
            className={cn("mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end", footerClassName)}
          >
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    portalNode
  )
}

export default Dialog
