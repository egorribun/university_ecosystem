export const PWA_REFRESH_EVENT = "pwa:need-refresh" as const
export const PUSH_EDUCATION_REQUEST_EVENT = "ecosystem:push-education-requested" as const

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
