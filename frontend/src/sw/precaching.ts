import { cleanupOutdatedCaches, matchPrecache, precacheAndRoute } from "workbox-precaching"
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
            // The SSR build creates the canonical shell as `_shell.html`;
            // `index.html` is mirrored only after Workbox injects the
            // manifest, so it is not a precached entry. `matchPrecache`
            // resolves the revisioned cache key correctly.
            return (await matchPrecache("_shell.html")) ?? Response.error()
          },
        },
      ],
    })
  )

  registerRoute(navigationRoute)
}
