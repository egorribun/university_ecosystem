import { logWarning } from "@/app/logger"
import { PUSH_SUBSCRIPTION_CHANGED_MESSAGE_TYPE } from "@/constants/serviceWorkerMessages"
import type { syncPushForConfirmedIdentity } from "./subscribe"

const installed = new WeakMap<ServiceWorkerContainer, WeakSet<ServiceWorkerRegistration>>()

/** Listen only to this registration's active worker, including before first claim. */
export function installPushSubscriptionChangeListener(
  container: ServiceWorkerContainer,
  registration: ServiceWorkerRegistration,
  sync: typeof syncPushForConfirmedIdentity
): void {
  const registrations = installed.get(container) ?? new WeakSet<ServiceWorkerRegistration>()
  if (registrations.has(registration)) return
  container.addEventListener("message", (event: MessageEvent) => {
    const active = registration.active
    if (!active || event.source !== active) return
    if (event.data?.type !== PUSH_SUBSCRIPTION_CHANGED_MESSAGE_TYPE) return
    void sync({ registration, subscriptionChange: true }).catch(() => {
      // Do not log endpoint, key, or account data from an unexpected failure.
      logWarning("Failed to sync push subscription after a worker notice")
    })
  })
  registrations.add(registration)
  installed.set(container, registrations)
}
