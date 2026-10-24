import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react"
import { m, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { sanitizeHttpUrl } from "@/utils/sanitize"
import { CheckCircle2, Info, AlertTriangle, XCircle, X, ExternalLink } from "lucide-react"
import { cn } from "@/utils/cn"
import { TIMEOUTS } from "@/config/timeouts"
import {
  getCurrentPushIdentitySnapshot,
  getCurrentPushUserId,
  getPushBufferStorageKey,
  subscribeToPushIdentity,
  subscribeToPushMessages,
} from "@/push/pushMessageBus"

const SERVER_AUTH_IDENTITY = Object.freeze({ userId: null, revision: 0 })
const getServerAuthIdentity = () => SERVER_AUTH_IDENTITY

type SnackbarSeverity = "success" | "info" | "warning" | "error"

export type ToastPayload = {
  id?: string
  title?: string
  body?: string
  url?: string
  icon?: string
  tag?: string
  data?: Record<string, unknown>
  timestamp?: number
}

export type ActiveToast = Required<Pick<ToastPayload, "id">> & ToastPayload
type OwnedActiveToast = { toast: ActiveToast; ownerId: string; ownerRevision: number }

type ServiceWorkerMessage = {
  type?: string
  toast?: ToastPayload
}

const VALID_SEVERITIES: readonly SnackbarSeverity[] = [
  "success",
  "info",
  "warning",
  "error",
] as const

const MAX_BUFFER_SIZE = 20
const LEGACY_BUFFER_STORAGE_KEY = "livePushToastBuffer"
const MAX_SEEN_TOAST_IDS = 256

/** @internal Browser snapshot used by the visibility subscription. */
export function getDocumentVisibility(): DocumentVisibilityState {
  return document.visibilityState
}

/** @internal SSR snapshot keeps hydration deterministic before a document exists. */
export function getServerVisibility(): DocumentVisibilityState {
  return "visible"
}

/** @internal Lifecycle subscription does not expose mutable snapshot state. */
export function getStableSnapshot(): null {
  return null
}

/** @internal Canonical defaults are exposed through a call so their contract is executable. */
export function getDefaultSeverity(): SnackbarSeverity {
  return "info"
}

/** @internal Storage keys are scoped to a confirmed account. */
export function getBufferStorageKey(userId: string): string {
  return getPushBufferStorageKey(userId)
}

/** @internal Pure normalizer exported for contract tests. */
function trimString(value: unknown): string | undefined {
  return typeof value === "string" ? value.trim() : undefined
}

/** @internal Restricts severity metadata to non-array records. */
export function isSeverityData(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

/** @internal Service-worker routing predicates are explicit and independently testable. */
export function shouldBufferPush(visibility: DocumentVisibilityState, isTestTransport: boolean) {
  return !isTestTransport && visibility !== "visible"
}

/** @internal Visibility listeners only flush when the document is visible. */
export function shouldFlushBufferedToasts(visibility: DocumentVisibilityState): boolean {
  return visibility === "visible"
}

/** @internal Distinguishes the message branch without coupling tests to React effects. */
export function isSyncCompleteMessage(type: string | undefined): boolean {
  return type === "SYNC_COMPLETE"
}

/** @internal Close timers are only cleared after a timer has actually been scheduled. */
export function hasCloseTimer(
  timer: ReturnType<typeof setTimeout> | null
): timer is ReturnType<typeof setTimeout> {
  return timer !== null
}

/** @internal Toast visibility requires both an open phase and a current item. */
export function shouldRenderToast(
  open: boolean,
  current: ActiveToast | null
): current is ActiveToast {
  return open && current !== null
}

/** @internal Keep title/body fallback behavior consistent in the view and tests. */
export function resolveToastContent(
  current: ActiveToast | null,
  translate: (key: string) => string
): { title: string; body: string } {
  return {
    title: current?.title?.trim() || translate("notifications:defaultTitle"),
    body: current?.body?.trim() || translate("notifications:defaultBody"),
  }
}

/** @internal Action callbacks may outlive the transient toast during exit. */
export function resolveToastActionUrl(current: ActiveToast | null): string | undefined {
  return current?.url
}

/**
 * Open the active toast action and dismiss the toast after the navigation has
 * been requested.  Keeping the action boundary outside the component makes
 * the transient no-active-toast state explicit and testable: a stale callback
 * must be a no-op instead of dereferencing a cleared toast.
 */
export function performToastAction(current: ActiveToast | null, onClose: () => void): void {
  const safeUrl = resolveToastActionUrl(current)
  if (!safeUrl) return
  try {
    const resolved = new URL(safeUrl, window.location.href)
    const sameOrigin = resolved.origin === window.location.origin
    window.open(resolved.href, getToastWindowTarget(sameOrigin), getToastWindowFeatures(sameOrigin))
  } catch (_error) {
    window.open(safeUrl, "_blank", "noopener,noreferrer")
  }
  onClose()
}

/** @internal Window target policy is same-origin aware and deterministic. */
export function getToastWindowTarget(sameOrigin: boolean): "_self" | "_blank" {
  return sameOrigin ? "_self" : "_blank"
}

/** @internal External actions receive an explicit opener-isolation feature string. */
export function getToastWindowFeatures(sameOrigin: boolean): string | undefined {
  return sameOrigin ? undefined : "noopener,noreferrer"
}

/** @internal Progress animation contract kept separate from the JSX tree. */
export function getToastProgressTransition(): { duration: number; ease: "linear" } {
  return { duration: 6, ease: "linear" }
}

/** @internal Clear a deferred close timer only when a timer exists. */
export function clearCloseTimer(timer: ReturnType<typeof setTimeout> | null): void {
  if (!hasCloseTimer(timer)) return
  clearTimeout(timer)
}

/** @internal Pure severity resolver shared by push and restored notifications. */
export const resolveSeverity = (toast: ActiveToast | null): SnackbarSeverity => {
  const data = toast?.data
  if (!isSeverityData(data)) return getDefaultSeverity()
  const rawSeverity = data.severity
  if (typeof rawSeverity !== "string") return getDefaultSeverity()
  const normalized = rawSeverity.trim().toLowerCase()
  const match = VALID_SEVERITIES.find((value) => value === normalized)
  return match ?? getDefaultSeverity()
}

/** @internal Canonical identity selection for deduplication. */
export const buildToastId = (toast: ToastPayload) => {
  const id = trimString(toast.id)
  if (id) return id
  const tag = trimString(toast.tag)
  if (tag) return tag
  if (Number.isFinite(toast.timestamp)) {
    return String(toast.timestamp)
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** @internal Validates and normalizes an untrusted service-worker payload. */
export function isToastPayload(payload: unknown): payload is ToastPayload {
  return payload !== null && typeof payload === "object" && !Array.isArray(payload)
}

export const toActiveToast = (payload: unknown): ActiveToast | null => {
  if (!isToastPayload(payload)) return null
  const toast = payload as ToastPayload
  const title = trimString(toast.title)
  const body = trimString(toast.body)
  const url = trimString(toast.url)
  const hasContent = Boolean(title || body)
  if (!hasContent) return null
  const safeUrl = url ? (sanitizeHttpUrl(url) ?? undefined) : undefined
  return { ...toast, title, body, id: buildToastId(toast), url: safeUrl }
}

/** Resolve browser storage without touching the window during SSR. */
export function getToastStorage(): Storage | null {
  if (typeof window === "undefined") return null
  const browserWindow = window
  try {
    return browserWindow.localStorage ?? null
  } catch {
    return null
  }
}

/** @internal Filters persisted data through the same untrusted-payload boundary. */
export const sanitizeBuffer = (buffer: unknown): ActiveToast[] => {
  if (!Array.isArray(buffer)) return []
  return buffer.map(toActiveToast).filter((item): item is ActiveToast => item !== null)
}

let memoryBuffer: ActiveToast[] = []
let memoryBufferUserId: string | null = null
let memoryBufferRevision: number | null = null

function clearMemoryBuffer(): void {
  memoryBuffer = []
  memoryBufferUserId = null
  memoryBufferRevision = null
}

const getCurrentBufferUserId = getCurrentPushUserId

/** @internal Legacy data has no trustworthy owner and is discarded without reading. */
function clearLegacyBuffer(): void {
  const storage = getToastStorage()
  if (storage === null) return
  try {
    const removeItem = storage.removeItem
    if (typeof removeItem === "function") removeItem.call(storage, LEGACY_BUFFER_STORAGE_KEY)
  } catch {
    // Ignore unavailable storage.
  }
}

/** @internal Clear only in-memory data; the message bus removes persisted data. */
function clearMemoryBufferForUser(userId: string): void {
  if (memoryBufferUserId !== userId) return
  memoryBuffer = []
  memoryBufferUserId = null
  memoryBufferRevision = null
}

/** @internal Storage read is deliberately fail-closed. */
export const readBuffer = (): ActiveToast[] => {
  const storage = getToastStorage()
  if (storage === null) {
    clearMemoryBuffer()
    return memoryBuffer
  }

  const identity = getCurrentPushIdentitySnapshot()
  const userId = identity.userId
  if (userId === null) {
    clearMemoryBuffer()
    return memoryBuffer
  }
  if (memoryBufferUserId !== userId || memoryBufferRevision !== identity.revision) {
    memoryBuffer = []
    memoryBufferUserId = userId
    memoryBufferRevision = identity.revision
  }

  const getItem = storage.getItem
  if (typeof getItem !== "function") {
    clearMemoryBuffer()
    return memoryBuffer
  }
  try {
    const raw = getItem.call(storage, getBufferStorageKey(userId))
    if (!raw) {
      memoryBuffer = []
      return memoryBuffer
    }
    const parsed = JSON.parse(raw) as unknown
    memoryBuffer = sanitizeBuffer(parsed)
    return memoryBuffer
  } catch {
    clearMemoryBuffer()
    return memoryBuffer
  }
}
/** @internal Storage write is best-effort and never breaks notification delivery. */
export const writeBuffer = (buffer: ActiveToast[]) => {
  const storage = getToastStorage()
  if (storage === null) {
    clearMemoryBuffer()
    return
  }

  const identity = getCurrentPushIdentitySnapshot()
  const userId = identity.userId
  if (userId === null) {
    clearMemoryBuffer()
    return
  }

  memoryBuffer = buffer.slice(-MAX_BUFFER_SIZE)
  memoryBufferUserId = userId
  memoryBufferRevision = identity.revision
  const setItem = storage.setItem
  if (typeof setItem !== "function") {
    clearMemoryBuffer()
    return
  }
  try {
    setItem.call(storage, getBufferStorageKey(userId), JSON.stringify(memoryBuffer))
  } catch (_e) {
    clearMemoryBuffer()
  }
}
export const bufferToast = (toast: ActiveToast) => {
  if (getCurrentBufferUserId() === null) return
  const existing = readBuffer()
  const deduped = existing.filter((item) => item.id !== toast.id)
  deduped.push(toast)
  writeBuffer(deduped)
}

export const consumeBufferedToasts = (): ActiveToast[] => {
  const buffered = readBuffer()
  if (buffered.length > 0) writeBuffer([])
  return buffered
}

/** @internal Bounded identity window used by both live and restored delivery. */
export const rememberToastId = (seenIds: Set<string>, id: string): boolean => {
  if (seenIds.has(id)) return false
  if (seenIds.size >= MAX_SEEN_TOAST_IDS) {
    const oldest = seenIds.values().next().value
    seenIds.delete(oldest!)
  }
  seenIds.add(id)
  return true
}

/** @internal Stable callback factory for account-bound toast enqueues. */
export function createToastEnqueueCallback(
  seenIdsRef: { current: Set<string> },
  append: (entry: { toast: ActiveToast; ownerId: string; ownerRevision: number }) => void
): (toast: ActiveToast, ownerId: string, ownerRevision: number) => void {
  return (toast, ownerId, ownerRevision) => {
    const currentIdentity = getCurrentPushIdentitySnapshot()
    if (currentIdentity.userId !== ownerId || currentIdentity.revision !== ownerRevision) return
    const seenIds = seenIdsRef.current
    if (!rememberToastId(seenIds, toast.id)) return
    append({ toast, ownerId, ownerRevision })
  }
}

export default function LivePushToasts() {
  const { t } = useTranslation(Array.of("notifications", "common"))
  const identitySnapshot = useSyncExternalStore(
    subscribeToPushIdentity,
    getCurrentPushIdentitySnapshot,
    getServerAuthIdentity
  )
  const confirmedUserId = identitySnapshot.userId
  const [queue, setQueue] = useState<OwnedActiveToast[]>([])
  const [current, setCurrent] = useState<OwnedActiveToast | null>(null)
  // `undefined` is the pre-render closed phase; explicit booleans are used after
  // the first transition so there is no duplicate initial-state sentinel.
  const [open, setOpen] = useState<boolean | undefined>()
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const seenToastIdsRef = useRef(new Set<string>())

  // Keep a stable callback identity, but construct the ref-reading enqueue
  // helper only when that callback runs after render.
  const [enqueue] = useState<(toast: ActiveToast, ownerId: string, ownerRevision: number) => void>(
    () => (toast: ActiveToast, ownerId: string, ownerRevision: number) => {
      createToastEnqueueCallback(seenToastIdsRef, (entry) => {
        setQueue((prev) => [...prev, entry])
      })(toast, ownerId, ownerRevision)
    }
  )

  const [flushBufferedToasts] = useState<() => void>(() => () => {
    const identity = getCurrentPushIdentitySnapshot()
    if (identity.userId === null) return
    const buffered = consumeBufferedToasts()
    // Restored messages keep the same account stamp as live bus deliveries.
    // This prevents a visibility flush from crossing an account transition.
    const ownerId = identity.userId
    buffered.forEach((toast) => enqueue(toast, ownerId, identity.revision))
  })

  const activeIdentityRef = useRef(identitySnapshot)
  useEffect(() => {
    clearLegacyBuffer()
    const previousIdentity = activeIdentityRef.current
    if (previousIdentity.revision === identitySnapshot.revision) {
      if (confirmedUserId !== null && shouldFlushBufferedToasts(document.visibilityState)) {
        flushBufferedToasts()
      }
      return
    }

    if (previousIdentity.userId !== null) clearMemoryBufferForUser(previousIdentity.userId)
    activeIdentityRef.current = identitySnapshot
    setQueue([])
    setCurrent(null)
    setOpen(false)
    seenToastIdsRef.current.clear()
    clearCloseTimer(closeTimerRef.current)
    closeTimerRef.current = null

    if (confirmedUserId !== null && shouldFlushBufferedToasts(document.visibilityState)) {
      flushBufferedToasts()
    }
  }, [confirmedUserId, flushBufferedToasts, identitySnapshot])
  useEffect(() => {
    const handleMessage = (event: MessageEvent, ownerId: string) => {
      if (ownerId !== getCurrentPushUserId()) return
      const data = event.data as ServiceWorkerMessage
      switch (data.type) {
        case "PUSH_NOTIFICATION": {
          const normalized = toActiveToast(data.toast)
          if (!normalized) return

          const isTest = window.name === "__mock_api_initialized__"
          if (shouldBufferPush(document.visibilityState, isTest)) {
            bufferToast(normalized)
            return
          }
          enqueue(normalized, ownerId, getCurrentPushIdentitySnapshot().revision)
          return
        }
        case "SYNC_COMPLETE": {
          const toast: ToastPayload = {
            title: t("notifications:sync.title"),
            body: t("notifications:sync.body"),
            data: { severity: "success" },
            timestamp: Date.now(),
          }
          const normalized = toActiveToast(toast)
          if (normalized) enqueue(normalized, ownerId, getCurrentPushIdentitySnapshot().revision)
          return
        }
      }
      return
    }

    return subscribeToPushMessages(handleMessage)
  }, [enqueue, t])

  const [subscribeVisibility] = useState<(onStoreChange: () => void) => () => void>(
    () => (onStoreChange: () => void) => {
      const flushWhenVisible = () => {
        if (!shouldFlushBufferedToasts(document.visibilityState)) return
        flushBufferedToasts()
      }
      const handleVisibilityChange = () => {
        flushWhenVisible()
        onStoreChange()
      }

      document.addEventListener("visibilitychange", handleVisibilityChange)
      flushWhenVisible()

      return () => document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  )
  useSyncExternalStore(subscribeVisibility, getDocumentVisibility, getServerVisibility)

  useEffect(() => {
    if (current || queue.length === 0) return
    const next = queue[0]!
    if (next.ownerId !== confirmedUserId || next.ownerRevision !== identitySnapshot.revision) {
      setQueue((prev) => prev.slice(1))
      return
    }
    setCurrent(next)
    setQueue((prev) => prev.slice(1))
    setOpen(true)
  }, [confirmedUserId, current, identitySnapshot.revision, queue])

  const [handleClose] = useState<() => void>(() => () => {
    setOpen(false)
    clearCloseTimer(closeTimerRef.current)
    closeTimerRef.current = setTimeout(() => {
      closeTimerRef.current = null
      setCurrent(null)
    }, 300)
  })

  const [subscribeLifecycle] = useState<() => () => void>(() => {
    return () => () => clearCloseTimer(closeTimerRef.current)
  })
  useSyncExternalStore(subscribeLifecycle, getStableSnapshot, getStableSnapshot)

  const currentToast = current?.toast ?? null
  const handleAction = useCallback(() => {
    performToastAction(currentToast, handleClose)
  }, [currentToast, handleClose])

  useEffect(() => {
    if (
      open &&
      currentToast &&
      current?.ownerId === confirmedUserId &&
      current?.ownerRevision === identitySnapshot.revision
    ) {
      const timer = setTimeout(handleClose, TIMEOUTS.TOAST_LONG)
      return () => clearTimeout(timer)
    }
  }, [confirmedUserId, current, currentToast, identitySnapshot.revision, open, handleClose])

  const severity = resolveSeverity(currentToast)
  const { title, body } = resolveToastContent(currentToast, t)

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
    <div
      key={identitySnapshot.revision}
      className="fixed top-4 right-4 z-toast flex flex-col gap-2 pointer-events-none"
    >
      <AnimatePresence>
        {shouldRenderToast(
          open === true &&
            current?.ownerId === confirmedUserId &&
            current?.ownerRevision === identitySnapshot.revision,
          currentToast
        ) && (
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
              className="pointer-events-none absolute inset-0 bg-linear-to-br from-white/[calc(var(--opacity-faint)*100%)] via-transparent to-transparent"
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

              {currentToast?.url && (
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
              onClick={() => handleClose()}
              className="group/btn relative z-base flex h-7 w-7 min-h-11 min-w-11 items-center justify-center rounded-full bg-linear-to-tr from-white/[calc(var(--opacity-faint)*100%)] to-white/[calc(var(--opacity-subtle)*100%)] text-(--text-secondary) transition-all duration-base hover:scale-110 hover:shadow-premium active:scale-95"
              aria-label={t("common:buttons.close")}
            >
              <X className="h-3.5 w-3.5 opacity-hover transition-opacity group-hover/btn:opacity-100" />
            </m.button>

            {/* Progress Bar — gradient style */}
            <div className="absolute bottom-0 left-0 right-0 h-0.5 overflow-hidden rounded-b-xl bg-white/[calc(var(--opacity-faint)*100%)]">
              <m.div
                className={cn("absolute bottom-0 left-0 h-0.5 opacity-heavy", severityIconColor)}
                style={{ background: "linear-gradient(to right, currentColor, transparent)" }}
                initial={{ width: "100%" }}
                animate={{ width: "0%" }}
                transition={getToastProgressTransition()}
              />
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
