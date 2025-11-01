import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type PropsWithChildren,
  type ReactNode,
} from "react"
import { createPortal } from "react-dom"
import { cn } from "@/utils/cn"
import { IconButton } from "./icon-button"

const isBrowser = typeof document !== "undefined"

const getToastRoot = () => {
  if (!isBrowser) return null
  const existing = document.getElementById("ue-toast-root")
  if (existing) return existing
  const node = document.createElement("div")
  node.setAttribute("id", "ue-toast-root")
  document.body.appendChild(node)
  return node
}

type ToastPosition = "top-right" | "top-left" | "bottom-right" | "bottom-left"

const viewportPosition: Record<ToastPosition, string> = {
  "top-right": "top-6 right-6 items-end",
  "top-left": "top-6 left-6 items-start",
  "bottom-right": "bottom-6 right-6 items-end",
  "bottom-left": "bottom-6 left-6 items-start",
}

export interface ToastViewportProps extends PropsWithChildren {
  position?: ToastPosition
  className?: string
  container?: HTMLElement | null
}

export function ToastViewport({ position = "bottom-right", className, container, children }: ToastViewportProps) {
  const portalNode = useMemo(() => container ?? getToastRoot(), [container])
  if (!portalNode) return null

  return createPortal(
    <div
      className={cn(
        "pointer-events-none fixed z-[var(--ue-z-index-toast)] flex w-full max-w-md flex-col gap-3",
        viewportPosition[position],
        className
      )}
    >
      {children}
    </div>,
    portalNode
  )
}

type ToastIntent = "info" | "success" | "warning" | "error"

const intentAccent: Record<ToastIntent, string> = {
  info: "border-l-[color:var(--nav-link)]",
  success: "border-l-[color:var(--badge-prac)]",
  warning: "border-l-[color:var(--badge-lab)]",
  error: "border-l-[color:var(--ue-form-error-border,rgba(220,38,38,0.8))]",
}

const intentIcon: Record<ToastIntent, string> = {
  info: "text-[color:var(--nav-link)]",
  success: "text-[color:var(--badge-prac)]",
  warning: "text-[color:var(--badge-lab)]",
  error: "text-[color:var(--ue-form-error-border,rgba(220,38,38,0.8))]",
}

export interface ToastProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title?: string
  description?: string
  intent?: ToastIntent
  duration?: number
  leadingIcon?: ReactNode
  actionLabel?: string
  onAction?: () => void
  dismissLabel?: string
  loading?: boolean
}

export function Toast({
  open,
  onOpenChange,
  title,
  description,
  intent = "info",
  duration = 6000,
  leadingIcon,
  actionLabel,
  onAction,
  dismissLabel = "Dismiss",
  loading = false,
}: ToastProps) {
  const [remaining, setRemaining] = useState(duration)
  const intervalRef = useRef<number | null>(null)
  const timeoutRef = useRef<number | null>(null)
  const elapsedRef = useRef(0)

  useEffect(() => {
    if (!open || duration <= 0) return undefined
    setRemaining(duration)
    elapsedRef.current = 0
    const step = Math.min(250, Math.max(60, Math.floor(duration / 20)))

    const tick = () => {
      elapsedRef.current = Math.min(duration, elapsedRef.current + step)
      const nextRemaining = Math.max(0, duration - elapsedRef.current)
      setRemaining(nextRemaining)
    }

    tick()
    intervalRef.current = window.setInterval(tick, step)
    timeoutRef.current = window.setTimeout(() => {
      elapsedRef.current = duration
      setRemaining(0)
      onOpenChange(false)
    }, duration)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
        elapsedRef.current = 0
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
    }
  }, [open, duration, onOpenChange])

  useEffect(() => {
    if (!open && intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
      elapsedRef.current = 0
    }
    if (!open && timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }, [open])

  const percent = duration > 0 ? Math.max(0, Math.min(100, (remaining / duration) * 100)) : 0

  const ariaLive = intent === "error" || intent === "warning" ? "assertive" : "polite"

  const handleClose = useCallback(() => onOpenChange(false), [onOpenChange])
  const handleAction = useCallback(() => {
    onAction?.()
  }, [onAction])

  if (!open) return null

  return (
    <div
      role="status"
      aria-live={ariaLive}
      className={cn(
        "pointer-events-auto overflow-hidden rounded-[var(--ue-radius-lg,1rem)] border bg-[color:var(--card-bg)]/98 p-4 text-[color:var(--page-text)] shadow-[0_28px_72px_rgba(15,23,42,0.32)]",
        "backdrop-blur-xl",
        intentAccent[intent]
      )}
      style={{ borderWidth: "1px", zIndex: 1 }}
    >
      <div className="flex items-start gap-3">
        <div className={cn("mt-0.5", intentIcon[intent])} aria-hidden>
          {leadingIcon ?? <DefaultToastIcon intent={intent} />}
        </div>
        <div className="flex flex-1 flex-col gap-1">
          {title ? <p className="text-sm font-semibold">{title}</p> : null}
          {description ? <p className="text-sm text-[color:var(--secondary-text)]">{description}</p> : null}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {actionLabel ? (
              <button
                type="button"
                onClick={handleAction}
                className="rounded-full border border-[color:var(--glass-border)] px-3 py-1 text-xs font-semibold text-[color:var(--nav-link)] transition-colors hover:bg-[color:var(--menu-hover-bg)] hover:text-[color:var(--menu-hover-text)] focus-visible:outline-none focus-visible:shadow-[var(--ue-focus-ring)]"
              >
                {actionLabel}
              </button>
            ) : null}
            {loading ? (
              <span className="ml-auto inline-flex items-center text-xs text-[color:var(--secondary-text)]">
                Loading…
              </span>
            ) : null}
          </div>
        </div>
        <IconButton
          aria-label={dismissLabel}
          variant="ghost"
          size="sm"
          onClick={handleClose}
          className="text-[color:var(--secondary-text)] hover:text-[color:var(--nav-link)]"
        >
          ×
        </IconButton>
      </div>
      {duration > 0 ? (
        <div className="mt-3 h-1 rounded-full bg-[color:rgba(148,163,184,0.25)]">
          <div
            className="h-full rounded-full bg-[color:var(--nav-link)] transition-[width] duration-150 ease-linear"
            style={{ width: `${percent}%` }}
            aria-hidden
          />
        </div>
      ) : null}
    </div>
  )
}

type DefaultToastIconProps = { intent: ToastIntent }

const DefaultToastIcon = ({ intent }: DefaultToastIconProps) => {
  if (intent === "success") {
    return <span className="text-lg">✓</span>
  }
  if (intent === "warning") {
    return <span className="text-lg">!</span>
  }
  if (intent === "error") {
    return <span className="text-lg">⚠️</span>
  }
  return <span className="text-lg">ℹ️</span>
}

export interface ToastActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {}

export const ToastActionButton = ({ className, ...rest }: ToastActionButtonProps) => (
  <button
    type="button"
    className={cn(
      "rounded-full border border-[color:var(--glass-border)] px-3 py-1 text-xs font-semibold text-[color:var(--nav-link)] transition-colors",
      "hover:bg-[color:var(--menu-hover-bg)] hover:text-[color:var(--menu-hover-text)]",
      "focus-visible:outline-none focus-visible:shadow-[var(--ue-focus-ring)]",
      className
    )}
    {...rest}
  />
)

ToastViewport.displayName = "ToastViewport"
Toast.displayName = "Toast"
ToastActionButton.displayName = "ToastActionButton"

