export async function collectNewsStartupErrors(page, waitForReady) {
  const consoleErrors = []
  const pageErrors = []
  const onConsole = (message) => {
    if (message.type() === "error" && !message.text().includes("favicon")) {
      consoleErrors.push(message.text())
    }
  }
  const onPageError = (error) => {
    if (
      !error.message.includes("ResizeObserver") &&
      !error.message.includes("AbortError") &&
      !error.message.includes("NetworkError")
    ) {
      pageErrors.push(error.message)
    }
  }
  page.on("console", onConsole)
  page.on("pageerror", onPageError)
  try {
    await page.goto("/news", { waitUntil: "commit", timeout: 30_000 })
    await page.waitForFunction(() => globalThis.window.__APP_HYDRATED === true, undefined, {
      timeout: 30_000,
    })
    await waitForReady()
    return {
      consoleErrors: consoleErrors.filter(
        (error) =>
          !error.includes("ResizeObserver") &&
          !error.includes("favicon") &&
          !error.includes("net::ERR_") &&
          !error.includes("Failed to load resource") &&
          !error.includes("status code 401")
      ),
      pageErrors,
    }
  } finally {
    page.off("console", onConsole)
    page.off("pageerror", onPageError)
  }
}
