import { PWA_REFRESH_EVENT, type ServiceWorkerUpdateEventDetail } from "@/app/pwaEvents"
import { createTrustedScriptURL } from "@/utils/trustedTypes"
import { logError } from "@/app/logger"
import {
  SERVICE_WORKER_MESSAGE_TYPES,
  type ServiceWorkerMessage,
} from "@/constants/serviceWorkerMessages"

const SKIP_WAITING_MESSAGE: ServiceWorkerMessage = {
  type: SERVICE_WORKER_MESSAGE_TYPES.SKIP_WAITING,
}
const PROCESS_QUEUE_MESSAGE: ServiceWorkerMessage = {
  type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE,
}

const notifyUpdateAvailable = (registration: ServiceWorkerRegistration) => {
  const detail: ServiceWorkerUpdateEventDetail = {
    update: async () => {
      if (registration.waiting && typeof registration.waiting.postMessage === "function") {
        registration.waiting.postMessage(SKIP_WAITING_MESSAGE)
      }
    },
  }

  window.dispatchEvent(
    new CustomEvent<ServiceWorkerUpdateEventDetail>(PWA_REFRESH_EVENT, { detail })
  )
}

const requestQueueProcessing = (registration: ServiceWorkerRegistration) => {
  const controller = navigator.serviceWorker.controller
  if (controller) {
    if (typeof controller.postMessage === "function") {
      controller.postMessage(PROCESS_QUEUE_MESSAGE)
    }
    return
  }

  if (registration.active && typeof registration.active.postMessage === "function") {
    registration.active.postMessage(PROCESS_QUEUE_MESSAGE)
  }
}

export async function registerServiceWorker(path = "/sw.js") {
  if (!("serviceWorker" in navigator)) return null
  const hadController = Boolean(navigator.serviceWorker.controller)

  try {
    const scriptUrl = createTrustedScriptURL(path)
    const registration = await navigator.serviceWorker.register(scriptUrl as unknown as string, {
      scope: "/",
      updateViaCache: "none",
    })

    await navigator.serviceWorker.ready

    const registerBackgroundSync = () => {
      if (!("sync" in registration)) return Promise.resolve()

      return (
        registration as ServiceWorkerRegistration & {
          sync: { register: (tag: string) => Promise<void> }
        }
      ).sync
        .register("sync-offline-mutations")
        .catch(() => {
          // Background Sync is optional; queue processing already falls back
          // to the controller/active-worker postMessage path.
        })
    }

    const sendQueueSignal = () => {
      if (typeof navigator.onLine === "boolean" && !navigator.onLine) {
        return
      }
      const backgroundSync = registerBackgroundSync()
      requestQueueProcessing(registration)
      return backgroundSync
    }

    sendQueueSignal()

    window.addEventListener("online", sendQueueSignal)
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        sendQueueSignal()
      }
    })

    if (registration.waiting && navigator.serviceWorker.controller) {
      notifyUpdateAvailable(registration)
    }

    if (registration && typeof registration.addEventListener === "function") {
      registration.addEventListener("updatefound", () => {
        const sw = registration.installing
        if (!sw) return

        const onStateChange = () => {
          if (sw.state === "installed" && navigator.serviceWorker.controller) {
            notifyUpdateAvailable(registration)
            sw.removeEventListener("statechange", onStateChange)
          }
        }

        sw.addEventListener("statechange", onStateChange)
      })
    }

    // A first install only begins controlling this already-current document;
    // reloading here can discard a form the user started while precaching ran.
    // Reload only when an existing controller is replaced by an update.
    let reloaded = false
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloaded || !hadController) return
      reloaded = true
      window.location.reload()
    })

    return registration
  } catch (error) {
    logError("Service worker registration failed", error)
    return null
  }
}
