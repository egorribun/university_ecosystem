const hasWindow = typeof window !== "undefined"

type Loader = () => Promise<unknown>

type PrefetchOptions = {
  timeoutMs?: number
}

const scheduled = new WeakSet<Loader>()

function schedule(fn: () => void, timeoutMs = 1200) {
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(fn, { timeout: timeoutMs })
    return
  }
  window.setTimeout(fn, timeoutMs)
}

export function prefetchRouteModules(loaders: Loader[], options: PrefetchOptions = {}): void {
  if (!hasWindow) return

  const uniqueLoaders = loaders.filter((loader) => {
    if (scheduled.has(loader)) return false
    scheduled.add(loader)
    return true
  })

  if (!uniqueLoaders.length) return

  schedule(() => {
    void Promise.allSettled(uniqueLoaders.map((loader) => loader()))
  }, options.timeoutMs)
}
