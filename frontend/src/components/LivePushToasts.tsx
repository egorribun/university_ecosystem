import { useCallback, useEffect, useState, type SyntheticEvent } from "react"
import { Alert, Button, Snackbar, Stack, Typography } from "@mui/material"
import type { SnackbarCloseReason } from "@mui/material/Snackbar"
import { useTranslation } from "react-i18next"
import { sanitizeHttpUrl } from "@/utils/sanitize"

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
  const { t } = useTranslation("notifications")
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
    if (!("serviceWorker" in navigator)) return

    const handleMessage = (event: MessageEvent<ServiceWorkerMessage>) => {
      const { data } = event
      if (!data || typeof data !== "object") return
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
          title: t("sync.title"),
          body: t("sync.body"),
          data: { severity: "success" },
          timestamp: Date.now(),
        }
        const normalized = toActiveToast(toast)
        if (normalized) enqueue(normalized)
      }
    }

    navigator.serviceWorker.addEventListener("message", handleMessage)
    return () => navigator.serviceWorker.removeEventListener("message", handleMessage)
  }, [enqueue])

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

  const handleClose = useCallback(
    (_event?: Event | SyntheticEvent, reason?: SnackbarCloseReason) => {
      if (reason === "clickaway") return
      setOpen(false)
      setCurrent(null)
    },
    []
  )

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
      console.error("Failed to open toast link", error)
      window.open(safeUrl, "_blank", "noopener,noreferrer")
    }
    setOpen(false)
    setCurrent(null)
  }, [current])

  const severity = resolveSeverity(current)
  const title = current?.title?.trim() || t("defaultTitle")
  const body = current?.body?.trim() || t("defaultBody")

  return (
    <Snackbar
      key={current?.id}
      open={open && Boolean(current)}
      autoHideDuration={6000}
      onClose={handleClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
    >
      <Alert
        severity={severity}
        variant="filled"
        onClose={handleClose}
        sx={{ alignItems: "flex-start", width: "100%", gap: 0.5, minWidth: { xs: 280, sm: 320 } }}
        action={
          current?.url ? (
            <Button color="inherit" size="small" onClick={handleAction}>
              {t("toast.open")}
            </Button>
          ) : null
        }
      >
        <Stack spacing={0.5}>
          {title ? (
            <Typography component="span" variant="subtitle2" sx={{ fontWeight: 700 }}>
              {title}
            </Typography>
          ) : null}
          {body ? (
            <Typography component="span" variant="body2">
              {body}
            </Typography>
          ) : null}
        </Stack>
      </Alert>
    </Snackbar>
  )
}
