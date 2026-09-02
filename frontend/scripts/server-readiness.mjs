export async function warmSsrRuntime(requestHandler, { url, timeoutMs = 60_000 } = {}) {
  if (
    !requestHandler ||
    typeof requestHandler.fetch !== "function" ||
    typeof url !== "string" ||
    !Number.isInteger(timeoutMs) ||
    timeoutMs < 1
  ) {
    throw new Error("SSR readiness warmup configuration is invalid")
  }

  const controller = new AbortController()
  let timer
  const timedOut = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller.abort()
      reject(new Error(`SSR readiness warmup exceeded ${timeoutMs}ms`))
    }, timeoutMs)
  })

  try {
    const response = await Promise.race([
      requestHandler.fetch(
        new Request(url, {
          headers: { accept: "text/html" },
          signal: controller.signal,
        })
      ),
      timedOut,
    ])
    if (!(response instanceof Response) || response.status !== 200) {
      await response?.body?.cancel()
      throw new Error(`SSR readiness warmup returned HTTP ${response?.status ?? "invalid"}`)
    }
    // A streaming SSR handler is not warm until its complete body has rendered;
    // awaiting only handler.fetch() would expose the same false-ready window.
    await Promise.race([response.arrayBuffer(), timedOut])
  } finally {
    clearTimeout(timer)
  }
}
