export const PWA_REFRESH_EVENT = "pwa:need-refresh" as const
export const PUSH_EDUCATION_REQUEST_EVENT = "ecosystem:push-education-requested" as const
export const SERVICE_WORKER_BOOTSTRAP_EVENT = "ecosystem:service-worker-bootstrap" as const

export type ServiceWorkerBootstrapStatus = "ready" | "unsupported" | "failed" | "disabled"
export type ServiceWorkerBootstrapEventDetail = {
  status: ServiceWorkerBootstrapStatus
}

export function dispatchServiceWorkerBootstrap(status: ServiceWorkerBootstrapStatus): void {
  if (typeof window === "undefined") return
  window.dispatchEvent(
    new CustomEvent<ServiceWorkerBootstrapEventDetail>(SERVICE_WORKER_BOOTSTRAP_EVENT, {
      detail: { status },
    })
  )
}

const PENDING_EDUCATION_TTL_MS = 30_000
let pendingEducation: { userId: string; requestedAt: number } | null = null

export function requestPushEducation(userId: string): void {
  pendingEducation = { userId, requestedAt: Date.now() }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(PUSH_EDUCATION_REQUEST_EVENT))
  }
}

export function consumePendingPushEducation(userId: string): boolean {
  const pending = pendingEducation
  pendingEducation = null
  return (
    pending !== null &&
    pending.userId === userId &&
    Date.now() - pending.requestedAt <= PENDING_EDUCATION_TTL_MS
  )
}

export type ServiceWorkerUpdateEventDetail = {
  update: () => Promise<void>
}

let pendingServiceWorkerUpdate: ServiceWorkerUpdateEventDetail | null = null

export function dispatchServiceWorkerUpdate(detail: ServiceWorkerUpdateEventDetail): void {
  if (typeof window === "undefined") return
  pendingServiceWorkerUpdate = detail
  window.dispatchEvent(
    new CustomEvent<ServiceWorkerUpdateEventDetail>(PWA_REFRESH_EVENT, { detail })
  )
}

export function getPendingServiceWorkerUpdate(): ServiceWorkerUpdateEventDetail | null {
  return pendingServiceWorkerUpdate
}

export function clearPendingServiceWorkerUpdate(
  detail: ServiceWorkerUpdateEventDetail | null
): void {
  if (pendingServiceWorkerUpdate === detail) {
    pendingServiceWorkerUpdate = null
  }
}
