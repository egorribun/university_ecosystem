export const PWA_REFRESH_EVENT = "pwa:need-refresh" as const

export type ServiceWorkerUpdateEventDetail = {
  update: () => Promise<void>
}




