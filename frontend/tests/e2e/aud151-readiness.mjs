export async function pageErrorsThroughReady(page, waitForReady) {
  const errors = []
  const onPageError = (error) => {
    if (
      !error.message.includes("ResizeObserver") &&
      !error.message.includes("AbortError") &&
      !error.message.includes("NetworkError")
    ) {
      errors.push(error.message)
    }
  }
  page.on("pageerror", onPageError)
  try {
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 30_000 })
    await page.waitForFunction(() => globalThis.window.__APP_HYDRATED === true, undefined, {
      timeout: 30_000,
    })
    await waitForReady()
    return errors
  } finally {
    page.off("pageerror", onPageError)
  }
}
