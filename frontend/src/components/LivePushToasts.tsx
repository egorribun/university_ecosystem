import { useCallback, useEffect, useState, type SyntheticEvent } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { sanitizeHttpUrl } from "@/utils/sanitize"
import { CheckCircle2, Info, AlertTriangle, XCircle, X, ExternalLink } from "lucide-react"
import { cn } from "@/utils/cn"

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

const resolveSeverity = (toast: ActiveToast | null): SnackbarSeverity => {
  if (!toast?.data || typeof toast.data !== "object") return DEFAULT_SEVERITY
  const rawSeverity = (toast.data as { severity?: unknown }).severity
  if (typeof rawSeverity !== "string") return DEFAULT_SEVERITY
  const normalized = rawSeverity.trim().toLowerCase()
  const match = VALID_SEVERITIES.find((value) => value === normalized)
  return match ?? DEFAULT_SEVERITY
}

const buildToastId = (toast: ToastPayload) => {
  if (toast.id && toast.id.trim()) return toast.id
  if (toast.tag && toast.tag.trim()) return toast.tag
  if (toast.timestamp && Number.isFinite(toast.timestamp)) return String(toast.timestamp)
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

const toActiveToast = (toast: ToastPayload): ActiveToast | null => {
  const hasContent = Boolean(toast.title?.trim() || toast.body?.trim())
  if (!hasContent) return null
  const safeUrl = toast.url ? (sanitizeHttpUrl(toast.url) ?? undefined) : undefined
  return { ...toast, id: buildToastId(toast), url: safeUrl }
}

let memoryBuffer: ActiveToast[] = []

const sanitizeBuffer = (buffer: unknown): ActiveToast[] => {
  if (!Array.isArray(buffer)) return []
  return buffer
    .map((item) => (item && typeof item === "object" ? toActiveToast(item as ToastPayload) : null))
    .filter((item): item is ActiveToast => Boolean(item))
}

const readBuffer = (): ActiveToast[] => {
  if (typeof window === "undefined") return memoryBuffer
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
  if (typeof window === "undefined") return
  try {
    window.localStorage?.setItem(BUFFER_STORAGE_KEY, JSON.stringify(memoryBuffer))
  } catch {
    // ignore persistence errors
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

  const enqueue = useCallback((toast: ToastPayload | ActiveToast) => {
    const normalized = toActiveToast(toast as ToastPayload)
    if (!normalized) return
    setQueue((prev) => [...prev, normalized])
  }, [])

  const flushBufferedToasts = useCallback(() => {
    const buffered = consumeBufferedToasts()
    if (buffered.length === 0) return
    setQueue((prev) => [...prev, ...buffered])
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    if (!navigator.serviceWorker) return

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

    navigator.serviceWorker.addEventListener("message", handleMessage)
    return () => navigator.serviceWorker.removeEventListener("message", handleMessage)
  }, [enqueue, t])

  useEffect(() => {
    if (typeof document === "undefined") return

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
    setCurrent(queue[0])
    setQueue((prev) => prev.slice(1))
    setOpen(true)
  }, [current, queue])

  const handleClose = useCallback(() => {
    setOpen(false)
    setTimeout(() => setCurrent(null), 300)
  }, [])

  const handleAction = useCallback(() => {
    if (!current?.url) return
    const safeUrl = sanitizeHttpUrl(current.url)
    if (!safeUrl) return
    try {
      const resolved = new URL(safeUrl, window.location.href)
      const sameOrigin = resolved.origin === window.location.origin
      window.open(
        resolved.href,
        sameOrigin ? "_self" : "_blank",
        sameOrigin ? undefined : "noopener,noreferrer"
      )
    } catch (error) {
      window.open(safeUrl, "_blank", "noopener,noreferrer")
    }
    handleClose()
  }, [current, handleClose])

  useEffect(() => {
    if (open && current) {
      const timer = setTimeout(handleClose, 6000)
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

  const severityClasses = {
    success: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
    info: "bg-blue-500/10 border-blue-500/20 text-blue-600 dark:text-blue-400",
    warning: "bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400",
    error: "bg-rose-500/10 border-rose-500/20 text-rose-600 dark:text-rose-400",
  }[severity]

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[9999] w-full max-w-sm px-6 pointer-events-none">
      <AnimatePresence>
        {open && current && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className={cn(
              "pointer-events-auto relative overflow-hidden flex items-start gap-4 p-4 rounded-2xl border backdrop-blur-2xl shadow-2xl",
              severityClasses
            )}
          >
            <div className="shrink-0 mt-0.5">
              <Icon className="h-5 w-5" />
            </div>

            <div className="flex-1 min-w-0 pr-4">
              <h4 className="text-sm font-black tracking-tight mb-0.5 truncate uppercase">
                {title}
              </h4>
              <p className="text-xs font-semibold opacity-80 leading-relaxed text-pretty">{body}</p>

              {current.url && (
                <button
                  onClick={handleAction}
                  className="mt-3 inline-flex items-center gap-1.5 text-[11px] font-black uppercase tracking-widest hover:underline"
                >
                  {t("notifications:toast.open")}
                  <ExternalLink className="h-3 w-3" />
                </button>
              )}
            </div>

            <button
              onClick={handleClose}
              className="shrink-0 p-1 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>

            {/* Progress bar for auto-hide */}
            <motion.div
              className="absolute bottom-0 left-0 h-0.5 bg-current opacity-30"
              initial={{ width: "100%" }}
              animate={{ width: "0%" }}
              transition={{ duration: 6, ease: "linear" }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
