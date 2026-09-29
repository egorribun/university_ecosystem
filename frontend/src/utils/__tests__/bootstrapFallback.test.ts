import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { waitFor, within } from "@testing-library/react"
import { getBootstrapFallbackCopy, renderBootstrapFallback } from "../bootstrapFallback"

const EN_COPY = {
  title: "We couldn't load the application",
  description:
    "Try refreshing the page or clearing your browser cache. If the issue persists, contact support.",
  reloadButtonLabel: "Reload page",
  clearCacheButtonLabel: "Clear cache and reload",
  clearingCacheLabel: "Clearing cache...",
}

const RU_COPY = {
  title: "Application failed to load / Не удалось загрузить приложение",
  description:
    "Please try to reload the page or clear your browser cache. If the problem persists, please contact support. / Попробуйте перезагрузить страницу или очистить кэш браузера. Если проблема сохраняется, обратитесь в поддержку.",
  reloadButtonLabel: "Reload Page / Перезагрузить страницу",
  clearCacheButtonLabel: "Clear Cache & Reload / Очистить кэш и перезагрузить",
  clearingCacheLabel: "Clearing cache / Очищаем кэш...",
}

function fakeDocument(options: {
  lang?: string
  bodyLang?: string | null
  defaultView?: unknown
}): Document {
  return {
    documentElement: { lang: options.lang ?? "" },
    body: options.bodyLang === null ? null : { lang: options.bodyLang ?? "" },
    defaultView: options.defaultView ?? null,
    createElement: document.createElement.bind(document),
  } as unknown as Document
}

describe("bootstrap fallback", () => {
  let root: HTMLElement

  beforeEach(() => {
    root = document.createElement("div")
    document.body.appendChild(root)
  })

  afterEach(() => {
    root.remove()
  })

  describe("getBootstrapFallbackCopy", () => {
    it("returns the full English and Russian dictionaries", () => {
      expect(getBootstrapFallbackCopy(fakeDocument({ lang: "en-GB" }))).toStrictEqual(EN_COPY)
      expect(getBootstrapFallbackCopy(fakeDocument({ lang: "RU" }))).toStrictEqual(RU_COPY)
    })

    it("prefers a supported document language over the body language", () => {
      expect(getBootstrapFallbackCopy(fakeDocument({ lang: "en", bodyLang: "ru" }))).toBe(
        getBootstrapFallbackCopy(fakeDocument({ lang: "en" }))
      )
      expect(getBootstrapFallbackCopy(fakeDocument({ lang: "en", bodyLang: "ru" })).title).toBe(
        EN_COPY.title
      )
    })

    it("falls back to the body language, then to English", () => {
      expect(getBootstrapFallbackCopy(fakeDocument({ lang: "fr", bodyLang: "ru" })).title).toBe(
        RU_COPY.title
      )
      expect(getBootstrapFallbackCopy(fakeDocument({ lang: "fr", bodyLang: "de" })).title).toBe(
        EN_COPY.title
      )
    })

    it("handles a document without a body", () => {
      expect(getBootstrapFallbackCopy(fakeDocument({ lang: "", bodyLang: null })).title).toBe(
        EN_COPY.title
      )
    })
  })

  describe("renderBootstrapFallback", () => {
    it("replaces the root content with an alert containing the copy and two buttons", () => {
      root.textContent = "stale application shell"

      const rendered = renderBootstrapFallback({
        documentRef: fakeDocument({ lang: "en" }),
        rootElement: root,
        copy: EN_COPY,
        logError: vi.fn(),
        onReload: vi.fn(),
      })

      expect(root.childNodes).toHaveLength(1)
      expect(root.firstChild).toBe(rendered.container)
      const alert = within(root).getByRole("alert")
      expect(within(alert).getByRole("heading", { level: 1 }).textContent).toBe(EN_COPY.title)
      expect(within(alert).getByText(EN_COPY.description).tagName).toBe("P")
      const reload = within(alert).getByRole("button", { name: EN_COPY.reloadButtonLabel })
      const clear = within(alert).getByRole("button", { name: EN_COPY.clearCacheButtonLabel })
      expect(reload).toBe(rendered.reloadButton)
      expect(clear).toBe(rendered.clearCacheButton)
      expect(reload.getAttribute("type")).toBe("button")
      expect(clear.getAttribute("type")).toBe("button")
      expect(root.textContent).not.toContain("stale application shell")
    })

    it("disables the clear-cache button while clearing and ignores repeated clicks", async () => {
      let finish: () => void = () => undefined
      const clearCachesAndReload = vi.fn(
        () =>
          new Promise<void>((resolve) => {
            finish = resolve
          })
      )
      const onReload = vi.fn()
      const rendered = renderBootstrapFallback({
        documentRef: fakeDocument({ lang: "en" }),
        rootElement: root,
        copy: EN_COPY,
        logError: vi.fn(),
        onReload,
        clearCachesAndReload,
      })

      rendered.clearCacheButton.click()
      rendered.clearCacheButton.click()

      expect(rendered.clearCacheButton.disabled).toBe(true)
      expect(rendered.clearCacheButton.textContent).toBe(EN_COPY.clearingCacheLabel)
      expect(clearCachesAndReload).toHaveBeenCalledOnce()
      expect(onReload).not.toHaveBeenCalled()

      finish()
      await waitFor(() => expect(onReload).toHaveBeenCalledOnce())
    })

    it("logs a failed cleanup with its error and still reloads", async () => {
      const cleanupError = new Error("quota")
      const logError = vi.fn()
      const onReload = vi.fn()
      const rendered = renderBootstrapFallback({
        documentRef: fakeDocument({ lang: "en" }),
        rootElement: root,
        copy: EN_COPY,
        logError,
        onReload,
        clearCachesAndReload: vi.fn().mockRejectedValue(cleanupError),
      })

      rendered.clearCacheButton.click()

      await waitFor(() => expect(onReload).toHaveBeenCalledOnce())
      expect(logError).toHaveBeenCalledExactlyOnceWith(
        "Failed to clear caches after bootstrap error",
        cleanupError
      )
    })

    it("unregisters every service worker and deletes every cache by default", async () => {
      const unregisterA = vi.fn().mockResolvedValue(true)
      const unregisterB = vi.fn().mockResolvedValue(true)
      const deleteCache = vi.fn().mockResolvedValue(true)
      const reload = vi.fn()
      const logError = vi.fn()
      const fakeWindow = {
        location: { reload },
        navigator: {
          serviceWorker: {
            getRegistrations: vi
              .fn()
              .mockResolvedValue([{ unregister: unregisterA }, { unregister: unregisterB }]),
          },
        },
        caches: { keys: vi.fn().mockResolvedValue(["shell-v1", "api-v2"]), delete: deleteCache },
      }
      const rendered = renderBootstrapFallback({
        documentRef: fakeDocument({ lang: "en", defaultView: fakeWindow }),
        rootElement: root,
        copy: EN_COPY,
        logError,
      })

      rendered.clearCacheButton.click()

      await waitFor(() => expect(reload).toHaveBeenCalledOnce())
      expect(unregisterA).toHaveBeenCalledOnce()
      expect(unregisterB).toHaveBeenCalledOnce()
      expect(deleteCache.mock.calls).toStrictEqual([["shell-v1"], ["api-v2"]])
      expect(logError).not.toHaveBeenCalled()
    })

    it("skips unsupported storage APIs without reporting an error", async () => {
      const reload = vi.fn()
      const logError = vi.fn()
      const rendered = renderBootstrapFallback({
        documentRef: fakeDocument({
          lang: "en",
          defaultView: { location: { reload }, navigator: {} },
        }),
        rootElement: root,
        copy: EN_COPY,
        logError,
      })

      rendered.clearCacheButton.click()

      await waitFor(() => expect(reload).toHaveBeenCalledOnce())
      expect(logError).not.toHaveBeenCalled()
    })
  })
})
