import { useCallback, useEffect, useState, type SyntheticEvent } from "react"
import { Alert, Button, Snackbar, Stack, Typography } from "@mui/material"
import type { SnackbarCloseReason } from "@mui/material/Snackbar"
import { useTranslation } from "react-i18next"

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

export default function LivePushToasts() {
  const { t } = useTranslation("notifications")
  const [queue, setQueue] = useState<ActiveToast[]>([])
  const [current, setCurrent] = useState<ActiveToast | null>(null)
  const [open, setOpen] = useState(false)

  const enqueue = useCallback((toast: ToastPayload) => {
    const hasContent = Boolean(toast.title?.trim() || toast.body?.trim())
    if (!hasContent) return
    setQueue((prev) => [...prev, { ...toast, id: buildToastId(toast) }])
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    if (!("serviceWorker" in navigator)) return

    const handleMessage = (event: MessageEvent<ServiceWorkerMessage>) => {
      const { data } = event
      if (!data || typeof data !== "object") return
      if (data.type !== "PUSH_NOTIFICATION") return
      if (!data.toast) return
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return
      enqueue(data.toast)
    }

    navigator.serviceWorker.addEventListener("message", handleMessage)
    return () => navigator.serviceWorker.removeEventListener("message", handleMessage)
  }, [enqueue])

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
    try {
      const resolved = new URL(current.url, window.location.href)
      const sameOrigin = resolved.origin === window.location.origin
      window.open(
        resolved.href,
        sameOrigin ? "_self" : "_blank",
        sameOrigin ? undefined : "noopener,noreferrer"
      )
    } catch (error) {
      console.error("Failed to open toast link", error)
      window.open(current.url, "_blank", "noopener,noreferrer")
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
