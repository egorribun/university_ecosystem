import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching"
import { NavigationRoute, registerRoute } from "workbox-routing"
import { NetworkOnly } from "workbox-strategies"

declare let self: ServiceWorkerGlobalScope

/**
 * Initialize precaching and basic navigation routing.
 */
export function initPrecaching() {
  // Precaching from VitePWA
  precacheAndRoute(self.__WB_MANIFEST)
  cleanupOutdatedCaches()

  // Basic navigation route (SPA shell)
  const navigationRoute = new NavigationRoute(
    new NetworkOnly({
      plugins: [
        {
          handlerDidError: async () => {
            // Offline fallback for navigation
            return (await self.caches.match("index.html")) || Response.error()
          },
        },
      ],
    })
  )

  registerRoute(navigationRoute)
}
