export type BootstrapFallbackLanguage = "en" | "ru"

export interface BootstrapFallbackCopy {
  title: string
  description: string
  reloadButtonLabel: string
  clearCacheButtonLabel: string
  clearingCacheLabel: string
}

const FALLBACK_DICTIONARY: Record<BootstrapFallbackLanguage, BootstrapFallbackCopy> = {
  en: {
    title: "We couldn't load the application",
    description:
      "Try refreshing the page or clearing your browser cache. If the issue persists, contact support.",
    reloadButtonLabel: "Reload page",
    clearCacheButtonLabel: "Clear cache and reload",
    clearingCacheLabel: "Clearing cache...",
  },
  ru: {
    title: "Не удалось загрузить приложение",
    description:
      "Попробуйте перезагрузить страницу или очистить кэш браузера. Если проблема сохраняется, обратитесь в поддержку.",
    reloadButtonLabel: "Перезагрузить страницу",
    clearCacheButtonLabel: "Очистить кэш и перезагрузить",
    clearingCacheLabel: "Очищаем кэш...",
  },
}

function normalizeLanguage(value: string | null | undefined): BootstrapFallbackLanguage | null {
  if (!value) {
    return null
  }

  const normalized = value.toLowerCase().split("-")[0]
  if (normalized === "en" || normalized === "ru") {
    return normalized
  }

  return null
}

export function getBootstrapFallbackCopy(documentRef: Document): BootstrapFallbackCopy {
  const detected = normalizeLanguage(documentRef.documentElement.lang) ??
    normalizeLanguage(documentRef.body?.lang)

  if (detected) {
    return FALLBACK_DICTIONARY[detected]
  }

  return FALLBACK_DICTIONARY.en
}

interface RenderBootstrapFallbackOptions {
  documentRef: Document
  rootElement: HTMLElement
  copy: BootstrapFallbackCopy
  logError: (message: string, error: unknown) => void
  onReload?: () => void
  clearCachesAndReload?: () => Promise<void>
}

export interface RenderedBootstrapFallback {
  container: HTMLDivElement
  reloadButton: HTMLButtonElement
  clearCacheButton: HTMLButtonElement
}

export function renderBootstrapFallback({
  documentRef,
  rootElement,
  copy,
  logError,
  onReload,
  clearCachesAndReload,
}: RenderBootstrapFallbackOptions): RenderedBootstrapFallback {
  const defaultWindow = documentRef.defaultView ?? window
  const reload =
    onReload ?? (() => {
      defaultWindow.location.reload()
    })

  const clearCaches = clearCachesAndReload
    ? clearCachesAndReload
    : async () => {
        if ("serviceWorker" in defaultWindow.navigator) {
          const registrations = await defaultWindow.navigator.serviceWorker.getRegistrations()
          await Promise.all(registrations.map((registration) => registration.unregister()))
        }

        if ("caches" in defaultWindow) {
          const cacheKeys = await defaultWindow.caches.keys()
          await Promise.all(cacheKeys.map((cacheKey) => defaultWindow.caches.delete(cacheKey)))
        }
      }

  rootElement.innerHTML = ""

  const container = documentRef.createElement("div")
  container.setAttribute("role", "alert")
  container.style.display = "flex"
  container.style.flexDirection = "column"
  container.style.alignItems = "center"
  container.style.justifyContent = "center"
  container.style.minHeight = "100vh"
  container.style.padding = "2rem"
  container.style.gap = "1.5rem"
  container.style.textAlign = "center"
  container.style.backgroundColor = "#f5f5f5"

  const title = documentRef.createElement("h1")
  title.textContent = copy.title
  title.style.margin = "0"
  title.style.fontSize = "1.75rem"

  const description = documentRef.createElement("p")
  description.textContent = copy.description
  description.style.margin = "0"
  description.style.maxWidth = "32rem"
  description.style.color = "#333"

  const actions = documentRef.createElement("div")
  actions.style.display = "flex"
  actions.style.flexWrap = "wrap"
  actions.style.gap = "1rem"
  actions.style.justifyContent = "center"

  const reloadButton = documentRef.createElement("button")
  reloadButton.type = "button"
  reloadButton.textContent = copy.reloadButtonLabel
  reloadButton.style.padding = "0.75rem 1.5rem"
  reloadButton.style.fontSize = "1rem"
  reloadButton.style.borderRadius = "9999px"
  reloadButton.style.border = "none"
  reloadButton.style.cursor = "pointer"
  reloadButton.style.backgroundColor = "#1976d2"
  reloadButton.style.color = "#fff"
  reloadButton.addEventListener("click", () => {
    reload()
  })

  const clearCacheButton = documentRef.createElement("button")
  clearCacheButton.type = "button"
  clearCacheButton.textContent = copy.clearCacheButtonLabel
  clearCacheButton.style.padding = "0.75rem 1.5rem"
  clearCacheButton.style.fontSize = "1rem"
  clearCacheButton.style.borderRadius = "9999px"
  clearCacheButton.style.border = "1px solid #1976d2"
  clearCacheButton.style.cursor = "pointer"
  clearCacheButton.style.backgroundColor = "transparent"
  clearCacheButton.style.color = "#1976d2"
  clearCacheButton.addEventListener("click", () => {
    if (clearCacheButton.disabled) {
      return
    }

    clearCacheButton.disabled = true
    clearCacheButton.textContent = copy.clearingCacheLabel

    void (async () => {
      try {
        await clearCaches()
      } catch (cleanupError) {
        logError("Failed to clear caches after bootstrap error", cleanupError)
      } finally {
        reload()
      }
    })()
  })

  actions.append(reloadButton, clearCacheButton)

  container.append(title, description, actions)

  rootElement.append(container)

  return {
    container,
    reloadButton,
    clearCacheButton,
  }
}
