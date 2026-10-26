import {
  dispatchServiceWorkerBootstrap,
  dispatchServiceWorkerUpdate,
  type ServiceWorkerUpdateEventDetail,
} from "@/app/pwaEvents"
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

const registrationTasksByContainer = new WeakMap<
  ServiceWorkerContainer,
  Map<string, Promise<ServiceWorkerRegistration | null>>
>()

const requestQueueProcessing = (
  registration: ServiceWorkerRegistration,
  serviceWorkerContainer: ServiceWorkerContainer
) => {
  const controller = serviceWorkerContainer.controller
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

export function registerServiceWorker(path = "/sw.js"): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) {
    dispatchServiceWorkerBootstrap("unsupported")
    return Promise.resolve(null)
  }

  const serviceWorkerContainer = navigator.serviceWorker
  const tasksByPath =
    registrationTasksByContainer.get(serviceWorkerContainer) ??
    new Map<string, Promise<ServiceWorkerRegistration | null>>()
  const existingTask = tasksByPath.get(path)
  if (existingTask) return existingTask

  const initialization = registerServiceWorkerOnce(path, serviceWorkerContainer)
  const sharedTask = initialization.then((registration) => {
    if (!registration) {
      tasksByPath.delete(path)
      if (tasksByPath.size === 0) {
        registrationTasksByContainer.delete(serviceWorkerContainer)
      }
    }
    return registration
  })
  tasksByPath.set(path, sharedTask)
  registrationTasksByContainer.set(serviceWorkerContainer, tasksByPath)
  return sharedTask
}

async function registerServiceWorkerOnce(
  path: string,
  serviceWorkerContainer: ServiceWorkerContainer
): Promise<ServiceWorkerRegistration | null> {
  try {
    const scriptUrl = createTrustedScriptURL(path)
    const registration = await serviceWorkerContainer.register(scriptUrl as unknown as string, {
      scope: "/",
      updateViaCache: "none",
    })

    await serviceWorkerContainer.ready

    type UpdateConsent = {
      accepted: boolean
      controllerChanged: boolean
      notified: boolean
    }
    const updateConsents = new WeakMap<ServiceWorker, UpdateConsent>()
    let reloadRequested = false
    const updateConsentFor = (worker: ServiceWorker): UpdateConsent => {
      const existing = updateConsents.get(worker)
      if (existing) return existing
      const consent: UpdateConsent = {
        accepted: false,
        controllerChanged: false,
        notified: false,
      }
      updateConsents.set(worker, consent)
      return consent
    }
    const reloadAfterAcceptedUpdate = (worker: ServiceWorker, consent: UpdateConsent) => {
      if (reloadRequested || !consent.accepted || !consent.controllerChanged) return
      if (serviceWorkerContainer.controller !== worker) return
      reloadRequested = true
      window.location.reload()
    }
    const showUpdateAvailable = (worker: ServiceWorker) => {
      const consent = updateConsentFor(worker)
      if (consent.notified) return
      consent.notified = true
      const detail: ServiceWorkerUpdateEventDetail = {
        update: async () => {
          // Consent belongs to this prompted worker, even if another tab has
          // already cleared registration.waiting and its controllerchange event
          // has not run in this page yet.
          consent.accepted = true
          if (registration.waiting === worker && typeof worker.postMessage === "function") {
            worker.postMessage(SKIP_WAITING_MESSAGE)
          }
          reloadAfterAcceptedUpdate(worker, consent)
        },
      }
      dispatchServiceWorkerUpdate(detail)
    }

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
      requestQueueProcessing(registration, serviceWorkerContainer)
      return backgroundSync
    }

    sendQueueSignal()

    window.addEventListener("online", sendQueueSignal)
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        sendQueueSignal()
      }
    })

    const waitingWorker = registration.waiting
    if (waitingWorker && serviceWorkerContainer.controller) {
      showUpdateAvailable(waitingWorker)
    }

    if (registration && typeof registration.addEventListener === "function") {
      registration.addEventListener("updatefound", () => {
        const sw = registration.installing
        if (!sw) return

        const onStateChange = () => {
          if (sw.state === "installed" && serviceWorkerContainer.controller) {
            showUpdateAvailable(sw)
            sw.removeEventListener("statechange", onStateChange)
          }
        }

        sw.addEventListener("statechange", onStateChange)
      })
    }

    // A first install only begins controlling this already-current document;
    // reloading here can discard a form the user started while precaching ran.
    // Consent and activation are paired by ServiceWorker object identity so
    // one tab's choice cannot authorize a later worker's controller change.
    // Compare worker identity because the first-claim event can still be queued
    // after ready resolves, even though its controller is already assigned.
    let observedController = serviceWorkerContainer.controller
    serviceWorkerContainer.addEventListener("controllerchange", () => {
      if (reloadRequested) return
      const currentController = serviceWorkerContainer.controller
      if (currentController === observedController) return
      const previousController = observedController
      observedController = currentController
      if (!previousController || !currentController) return
      const consent = updateConsentFor(currentController)
      consent.controllerChanged = true
      showUpdateAvailable(currentController)
      reloadAfterAcceptedUpdate(currentController, consent)
    })

    dispatchServiceWorkerBootstrap("ready")
    return registration
  } catch (error) {
    dispatchServiceWorkerBootstrap("failed")
    logError("Service worker registration failed", error)
    return null
  }
}
