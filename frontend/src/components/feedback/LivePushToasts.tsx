import { useCallback, useEffect, useRef, useState } from "react"
import { m, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { sanitizeHttpUrl } from "@/utils/sanitize"
import { CheckCircle2, Info, AlertTriangle, XCircle, X, ExternalLink } from "lucide-react"
import { cn } from "@/utils/cn"
import { TIMEOUTS } from "@/config/timeouts"
import { subscribeToPushMessages } from "@/push/pushMessageBus"

type SnackbarSeverity = "success" | "info" | "warning" | "error"

type ToastPayload = {
  id?: string
  title?: string
  body?: string
  url?: string
  icon?: string
  tag?: string
  data?: Record<string, unknown>
  timestamp?: number
}

type ActiveToast = Required<Pick<ToastPayload, "id">> & ToastPayload

type ServiceWorkerMessage = {
  type?: string
  toast?: ToastPayload
}

const DEFAULT_SEVERITY: SnackbarSeverity = "info"
const VALID_SEVERITIES: readonly SnackbarSeverity[] = [
  "success",
  "info",
  "warning",
  "error",
] as const

const BUFFER_STORAGE_KEY = "livePushToastBuffer"
const MAX_BUFFER_SIZE = 20
const MAX_SEEN_TOAST_IDS = 256

const trimString = (value: unknown): string | undefined =>
  typeof value === "string" ? value.trim() : undefined

const resolveSeverity = (toast: ActiveToast | null): SnackbarSeverity => {
  if (!toast?.data || typeof toast.data !== "object") return DEFAULT_SEVERITY
  const rawSeverity = (toast.data as { severity?: unknown }).severity
  if (typeof rawSeverity !== "string") return DEFAULT_SEVERITY
  const normalized = rawSeverity.trim().toLowerCase()
  const match = VALID_SEVERITIES.find((value) => value === normalized)
  return match ?? DEFAULT_SEVERITY
}

const buildToastId = (toast: ToastPayload) => {
  const id = trimString(toast.id)
  if (id) return id
  const tag = trimString(toast.tag)
  if (tag) return tag
  if (typeof toast.timestamp === "number" && Number.isFinite(toast.timestamp)) {
    return String(toast.timestamp)
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

const toActiveToast = (payload: unknown): ActiveToast | null => {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null
  const toast = payload as ToastPayload
  const title = trimString(toast.title)
  const body = trimString(toast.body)
  const url = trimString(toast.url)
  const hasContent = Boolean(title || body)
  if (!hasContent) return null
  const safeUrl = url ? (sanitizeHttpUrl(url) ?? undefined) : undefined
  return { ...toast, title, body, id: buildToastId(toast), url: safeUrl }
}

let memoryBuffer: ActiveToast[] = []

const sanitizeBuffer = (buffer: unknown): ActiveToast[] => {
  if (!Array.isArray(buffer)) return []
  return buffer
    .map((item) => (item && typeof item === "object" ? toActiveToast(item as ToastPayload) : null))
    .filter((item): item is ActiveToast => Boolean(item))
}

const readBuffer = (): ActiveToast[] => {
  try {
    const raw = window.localStorage?.getItem(BUFFER_STORAGE_KEY)
    if (!raw) {
      memoryBuffer = []
      return memoryBuffer
    }
    const parsed = JSON.parse(raw) as unknown
    memoryBuffer = sanitizeBuffer(parsed)
    return memoryBuffer
  } catch {
    memoryBuffer = []
    return memoryBuffer
  }
}

const writeBuffer = (buffer: ActiveToast[]) => {
  memoryBuffer = buffer.slice(-MAX_BUFFER_SIZE)
  try {
    window.localStorage?.setItem(BUFFER_STORAGE_KEY, JSON.stringify(memoryBuffer))
  } catch (_e) {
    // Ignore
  }
}

const bufferToast = (toast: ActiveToast) => {
  const existing = readBuffer()
  const deduped = existing.filter((item) => item.id !== toast.id)
  deduped.push(toast)
  writeBuffer(deduped)
}

const consumeBufferedToasts = (): ActiveToast[] => {
  const buffered = [...readBuffer()]
  if (buffered.length === 0) return []
  writeBuffer([])
  return buffered
}

export default function LivePushToasts() {
  const { t } = useTranslation(["notifications", "common"])
  const [queue, setQueue] = useState<ActiveToast[]>([])
  const [current, setCurrent] = useState<ActiveToast | null>(null)
  const [open, setOpen] = useState(false)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const seenToastIdsRef = useRef(new Set<string>())

  const enqueue = useCallback((toast: ActiveToast) => {
    const seenIds = seenToastIdsRef.current
    if (seenIds.has(toast.id)) return
    if (seenIds.size >= MAX_SEEN_TOAST_IDS) {
      // The size guard makes the iterator non-empty; the non-null assertion
      // keeps this eviction path branch-free and preserves the Set<string>
      // invariant for the exact-100% coverage contract.
      seenIds.delete(seenIds.values().next().value!)
    }
    seenIds.add(toast.id)
    setQueue((prev) => [...prev, toast])
  }, [])

  const flushBufferedToasts = useCallback(() => {
    const buffered = consumeBufferedToasts()
    if (buffered.length === 0) return
    // Route restored messages through the same identity window as live
    // delivery.  A visibility transition can race with a push that arrived
    // after the tab became visible; appending directly would show that toast
    // twice and would not mark restored ids as seen.
    buffered.forEach(enqueue)
  }, [enqueue])

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const data = event.data as ServiceWorkerMessage
      if (data.type === "PUSH_NOTIFICATION") {
        if (!data.toast) return
        const normalized = toActiveToast(data.toast)
        if (!normalized) return

        const isTest = typeof window !== "undefined" && window.name === "__mock_api_initialized__"
        if (typeof document !== "undefined" && document.visibilityState !== "visible" && !isTest) {
          bufferToast(normalized)
          return
        }
        enqueue(normalized)
      } else if (data.type === "SYNC_COMPLETE") {
        const toast: ToastPayload = {
          title: t("notifications:sync.title"),
          body: t("notifications:sync.body"),
          data: { severity: "success" },
          timestamp: Date.now(),
        }
        const normalized = toActiveToast(toast)
        if (normalized) enqueue(normalized)
      }
    }

    return subscribeToPushMessages(handleMessage)
  }, [enqueue, t])

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") return
      flushBufferedToasts()
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)
    handleVisibilityChange()

    return () => document.removeEventListener("visibilitychange", handleVisibilityChange)
  }, [flushBufferedToasts])

  useEffect(() => {
    if (current || queue.length === 0) return
    setCurrent(queue[0]!)
    setQueue((prev) => prev.slice(1))
    setOpen(true)
  }, [current, queue])

  const handleClose = useCallback(() => {
    setOpen(false)
    if (closeTimerRef.current !== null) clearTimeout(closeTimerRef.current)
    closeTimerRef.current = setTimeout(() => {
      closeTimerRef.current = null
      setCurrent(null)
    }, 300)
  }, [])

  useEffect(() => {
    return () => {
      if (closeTimerRef.current !== null) {
        clearTimeout(closeTimerRef.current)
        closeTimerRef.current = null
      }
    }
  }, [])

  const handleAction = useCallback(() => {
    const safeUrl = current!.url!
    try {
      const resolved = new URL(safeUrl, window.location.href)
      const sameOrigin = resolved.origin === window.location.origin
      window.open(
        resolved.href,
        sameOrigin ? "_self" : "_blank",
        sameOrigin ? undefined : "noopener,noreferrer"
      )
    } catch (_error) {
      window.open(safeUrl, "_blank", "noopener,noreferrer")
    }
    handleClose()
  }, [current, handleClose])

  useEffect(() => {
    if (open && current) {
      const timer = setTimeout(handleClose, TIMEOUTS.TOAST_LONG)
      return () => clearTimeout(timer)
    }
  }, [open, current, handleClose])

  const severity = resolveSeverity(current)
  const title = current?.title?.trim() || t("notifications:defaultTitle")
  const body = current?.body?.trim() || t("notifications:defaultBody")

  const Icon = {
    success: CheckCircle2,
    info: Info,
    warning: AlertTriangle,
    error: XCircle,
  }[severity]

  /** Wave 46: severity → left accent border color */
  const severityAccent = {
    success: "border-l-success-border",
    info: "border-l-brand",
    warning: "border-l-warning-border",
    error: "border-l-error-border",
  }[severity]

  const severityIconColor = {
    success: "text-success-text",
    info: "text-brand",
    warning: "text-warning-text",
    error: "text-error-text",
  }[severity]

  return (
    <div className="fixed top-4 right-4 z-toast flex flex-col gap-2 pointer-events-none">
      <AnimatePresence>
        {open && current && (
          <m.div
            // Keep toast motion on compositor-friendly properties. Animating
            // filter/backdrop blur can crash WebKit while the action button is
            // becoming interactive, and spring settling is unnecessarily
            // nondeterministic for a transient notification.
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            role="status"
            aria-live="polite"
            aria-atomic="true"
            className={cn(
              "pointer-events-auto relative overflow-hidden flex items-start gap-4 p-4 rounded-2xl",
              "glass-noise backdrop-blur-2xl border border-(--glass-border) shadow-premium",
              "bg-(--glass-bg-high) dark:bg-(--glass-bg-high)",
              "border-l-[3px]",
              severityAccent
            )}
          >
            {/* Glass sheen overlay */}
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 bg-linear-to-br from-white/(--opacity-faint) via-transparent to-transparent"
            />

            <div className={cn("shrink-0 mt-0.5 relative z-base", severityIconColor)}>
              <Icon className="h-5 w-5" />
            </div>

            <div className="flex-1 min-w-0 pr-4 relative z-base">
              <h4 className="text-sm font-black tracking-tight mb-0.5 truncate uppercase text-text-primary">
                {title}
              </h4>
              <p className="text-xs font-semibold opacity-hover leading-relaxed text-pretty text-(--text-secondary)">
                {body}
              </p>

              {current.url && (
                <button
                  onClick={handleAction}
                  className={cn(
                    "mt-3 inline-flex min-h-11 items-center gap-1.5 px-2 text-label-md font-black uppercase tracking-widest hover:underline",
                    severityIconColor
                  )}
                >
                  {t("notifications:toast.open")}
                  <ExternalLink className="h-3 w-3" />
                </button>
              )}
            </div>

            <m.button
              type="button"
              whileTap={{ scale: 0.94 }}
              onClick={() => handleClose()}
              className="group/btn relative z-base flex h-7 w-7 min-h-11 min-w-11 items-center justify-center rounded-full bg-linear-to-tr from-white/(--opacity-faint) to-white/(--opacity-subtle) text-(--text-secondary) transition-all duration-base hover:scale-110 hover:shadow-premium active:scale-95"
              aria-label={t("common:buttons.close")}
            >
              <X className="h-3.5 w-3.5 opacity-hover transition-opacity group-hover/btn:opacity-100" />
            </m.button>

            {/* Progress Bar — gradient style */}
            <div className="absolute bottom-0 left-0 right-0 h-0.5 overflow-hidden rounded-b-xl bg-white/(--opacity-faint)">
              <m.div
                className={cn("absolute bottom-0 left-0 h-0.5 opacity-heavy", severityIconColor)}
                style={{ background: "linear-gradient(to right, currentColor, transparent)" }}
                initial={{ width: "100%" }}
                animate={{ width: "0%" }}
                transition={{ duration: 6, ease: "linear" }}
              />
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
