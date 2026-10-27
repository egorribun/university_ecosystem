export function publishPwaBuildMarker(marker: string): void {
  Reflect.set(window, "__UE_PWA_TEST_BUILD_MARKER__", marker)
}

export function createPwaBuildMarkerScript(marker: string): string {
  return `\n;(${publishPwaBuildMarker.toString()})(${JSON.stringify(marker)});\n`
}

export async function readPrecachedModuleAppBundleEvidence() {
  const bundleScripts = [...document.scripts]
    .filter((script) => script.type === "module" && script.src !== "")
    .map((script) => {
      const scriptUrl = new URL(script.src)
      return {
        origin: scriptUrl.origin,
        pathname: scriptUrl.pathname,
      }
    })

  const precacheNames = (await caches.keys()).filter((name) => name.startsWith("workbox-precache"))
  const precacheEntries = (
    await Promise.all(
      precacheNames.map(async (cacheName) => {
        const cache = await caches.open(cacheName)
        return (await cache.keys()).map((request) => {
          const requestUrl = new URL(request.url)
          return {
            cacheName,
            requestUrl: request.url,
            path: requestUrl.pathname,
            origin: requestUrl.origin,
          }
        })
      })
    )
  ).flat()

  const appBundlePath =
    bundleScripts.find(
      (script) =>
        script.origin === location.origin &&
        script.pathname.startsWith("/assets/") &&
        script.pathname.endsWith(".js") &&
        precacheEntries.some(
          (entry) => entry.origin === location.origin && entry.path === script.pathname
        )
    )?.pathname ?? null

  return { appBundlePath, precacheEntries }
}
