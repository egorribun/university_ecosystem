import { PWA_REFRESH_EVENT, type ServiceWorkerUpdateEventDetail } from "../app/pwaEvents"

const SKIP_WAITING_MESSAGE = { type: "SKIP_WAITING" } as const
const PROCESS_QUEUE_MESSAGE = { type: "PROCESS_NOTIFICATION_CLICK_QUEUE" } as const

const notifyUpdateAvailable = (registration: ServiceWorkerRegistration) => {
  const detail: ServiceWorkerUpdateEventDetail = {
    update: async () => {
      registration.waiting?.postMessage(SKIP_WAITING_MESSAGE)
    },
  }

  window.dispatchEvent(
    new CustomEvent<ServiceWorkerUpdateEventDetail>(PWA_REFRESH_EVENT, { detail })
  )
}

const requestQueueProcessing = (registration: ServiceWorkerRegistration) => {
  const controller = navigator.serviceWorker.controller
  if (controller) {
    controller.postMessage(PROCESS_QUEUE_MESSAGE)
    return
  }

  registration.active?.postMessage(PROCESS_QUEUE_MESSAGE)
}

export async function registerServiceWorker(path = "/sw.js") {
  if (!("serviceWorker" in navigator)) return null

  try {
    const registration = await navigator.serviceWorker.register(path, {
      scope: "/",
      updateViaCache: "none",
    })

    await navigator.serviceWorker.ready

    const sendQueueSignal = () => {
      if (typeof navigator.onLine === "boolean" && !navigator.onLine) {
        return
      }
      requestQueueProcessing(registration)
    }

    sendQueueSignal()

    window.addEventListener("online", sendQueueSignal)

    if (registration.waiting && navigator.serviceWorker.controller) {
      notifyUpdateAvailable(registration)
    }

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

    let reloaded = false
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloaded) return
      reloaded = true
      window.location.reload()
    })

    return registration
  } catch (error) {
    console.error("Service worker registration failed", error)
    return null
  }
}
