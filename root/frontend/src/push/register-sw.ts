export async function registerServiceWorker(path = "/sw.js") {
  if (!("serviceWorker" in navigator)) return null
  try {
    const reg = await navigator.serviceWorker.register(path, { scope: "/", updateViaCache: "none" })
    await navigator.serviceWorker.ready

    if (reg.waiting && navigator.serviceWorker.controller) {
      reg.waiting.postMessage({ type: "SKIP_WAITING" })
    }

    reg.addEventListener("updatefound", () => {
      const sw = reg.installing
      if (!sw) return
      const onState = () => {
        if (sw.state === "installed" && navigator.serviceWorker.controller) {
          reg.waiting?.postMessage({ type: "SKIP_WAITING" })
        }
      }
      sw.addEventListener("statechange", onState, { once: false })
    })

    let reloaded = false
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloaded) return
      reloaded = true
      window.location.reload()
    })

    return reg
  } catch {
    return null
  }
}