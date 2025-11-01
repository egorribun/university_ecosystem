import { createPortal } from "react-dom"
import {
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react"
import { cn } from "@/utils/cn"

const sizeVariants = {
  sm: "max-w-md",
  md: "max-w-xl",
  lg: "max-w-3xl",
} as const

type ModalSize = keyof typeof sizeVariants

type ModalProps = {
  open: boolean
  onClose: () => void
  labelledBy?: string
  describedBy?: string
  children: ReactNode
  className?: string
  panelClassName?: string
  size?: ModalSize
  fullScreenOnMobile?: boolean
  closeOnBackdrop?: boolean
}

const useIsClient = () => {
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])
  return mounted
}

const focusableSelectors = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
]

export function Modal({
  open,
  onClose,
  labelledBy,
  describedBy,
  className,
  panelClassName,
  size = "md",
  children,
  fullScreenOnMobile = false,
  closeOnBackdrop = true,
}: ModalProps) {
  const isClient = useIsClient()
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const body = document.body
    const previous = body.style.overflow
    body.style.overflow = "hidden"
    return () => {
      body.style.overflow = previous
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation()
        onClose()
      }
      if (event.key === "Tab") {
        const panel = document.getElementById(panelId)
        if (!panel) return
        const focusable = Array.from(
          panel.querySelectorAll<HTMLElement>(focusableSelectors.join(",")),
        ).filter((el) => !el.hasAttribute("data-modal-focus-guard"))
        if (focusable.length === 0) {
          event.preventDefault()
          return
        }
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (event.shiftKey) {
          if (document.activeElement === first) {
            event.preventDefault()
            last.focus()
          }
        } else if (document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }

    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [onClose, open, panelId])

  const handleBackdropClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (!closeOnBackdrop) return
      if (event.target === event.currentTarget) onClose()
    },
    [closeOnBackdrop, onClose],
  )

  const portalTarget = useMemo(() => {
    if (!isClient || typeof document === "undefined") return null
    return document.body
  }, [isClient])

  if (!open || !portalTarget) return null

  return createPortal(
    <div
      className={cn(
        "fixed inset-0 z-[var(--ue-z-index-overlay,2147483600)] flex items-center justify-center px-4 py-10 sm:px-6",
        className,
      )}
      role="presentation"
      onMouseDown={handleBackdropClick}
    >
      <div
        className="absolute inset-0 -z-10 bg-[color:var(--modal-scrim,rgba(15,23,42,0.45))] backdrop-blur-[4px]"
        aria-hidden="true"
      />
      <div
        id={panelId}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        className={cn(
          "relative w-full overflow-hidden rounded-ue-2xl border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.4))_70%,transparent_30%)] bg-[color:var(--page-bg,#fff)] text-[color:var(--page-text)] shadow-[0_30px_60px_rgba(15,23,42,0.16)] focus:outline-none",
          sizeVariants[size],
          fullScreenOnMobile
            ? "max-h-[min(96vh,720px)] sm:max-h-[85vh] sm:rounded-ue-2xl"
            : "max-h-[min(90vh,720px)]",
          fullScreenOnMobile ? "h-[min(96vh,720px)] sm:h-auto" : "",
          panelClassName,
        )}
        tabIndex={-1}
      >
        <div className="flex h-full flex-col overflow-hidden">
          <span data-modal-focus-guard tabIndex={0} className="sr-only">
            {" "}
          </span>
          <div className="relative flex-1 overflow-y-auto">{children}</div>
          <span data-modal-focus-guard tabIndex={0} className="sr-only">
            {" "}
          </span>
        </div>
      </div>
    </div>,
    portalTarget,
  )
}

type ModalSectionProps = {
  children: ReactNode
  className?: string
}

type ModalHeaderProps = ModalSectionProps & {
  titleId?: string
  actions?: ReactNode
}

export function ModalHeader({ children, className, titleId, actions }: ModalHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 border-b border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.38))_60%,transparent_40%)] bg-[color:var(--modal-header-bg,rgba(241,245,255,0.72))] px-6 py-5",
        className,
      )}
    >
      <h2
        id={titleId}
        className="text-lg font-semibold leading-tight text-[color:var(--page-text)]"
      >
        {children}
      </h2>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function ModalBody({ children, className }: ModalSectionProps) {
  return <div className={cn("px-6 py-5", className)}>{children}</div>
}

export function ModalFooter({ children, className }: ModalSectionProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-end gap-3 border-t border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.32))_60%,transparent_40%)] bg-[color:var(--modal-footer-bg,rgba(248,250,255,0.75))] px-6 py-4",
        className,
      )}
    >
      {children}
    </div>
  )
}

export const modalFieldStyles = {
  label: "flex flex-col gap-2 text-sm font-semibold text-[color:color-mix(in_srgb,var(--page-text)_65%,white_35%)]",
  input:
    "w-full rounded-ue-xl border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.38))_70%,transparent_30%)] bg-[color:color-mix(in_srgb,var(--page-bg,#fff)_85%,white_15%)] px-4 py-3 text-[color:var(--page-text)] shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-4 focus:ring-[color:var(--nav-link)]/15",
  textarea:
    "min-h-[140px] w-full rounded-ue-xl border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.38))_70%,transparent_30%)] bg-[color:color-mix(in_srgb,var(--page-bg,#fff)_85%,white_15%)] px-4 py-3 text-[color:var(--page-text)] shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-4 focus:ring-[color:var(--nav-link)]/15",
  helper: "text-xs font-medium text-[color:color-mix(in_srgb,var(--secondary-text,#64748b)_86%,white_14%)]",
}

export default Modal
