import { afterEach, describe, expect, it, vi } from "vitest"

import {
  getBootstrapFallbackCopy,
  renderBootstrapFallback,
} from "../utils/bootstrapFallback"

afterEach(() => {
  document.body.innerHTML = ""
  document.documentElement.lang = ""
  vi.restoreAllMocks()
})

describe("bootstrap fallback", () => {
  it("renders English copy and keeps button behaviors", async () => {
    document.documentElement.lang = "en"
    const rootElement = document.createElement("div")
    document.body.append(rootElement)

    const copy = getBootstrapFallbackCopy(document)
    const onReload = vi.fn()
    const clearCachesAndReload = vi.fn().mockResolvedValue(undefined)
    const logError = vi.fn()

    const { reloadButton, clearCacheButton, container } = renderBootstrapFallback({
      documentRef: document,
      rootElement,
      copy,
      logError,
      onReload,
      clearCachesAndReload,
    })

    expect(container.querySelector("h1")?.textContent).toBe(copy.title)
    expect(container.querySelector("p")?.textContent).toBe(copy.description)
    expect(reloadButton.textContent).toBe(copy.reloadButtonLabel)
    expect(clearCacheButton.textContent).toBe(copy.clearCacheButtonLabel)

    reloadButton.click()
    expect(onReload).toHaveBeenCalledTimes(1)

    clearCacheButton.click()

    expect(clearCacheButton.disabled).toBe(true)
    expect(clearCacheButton.textContent).toBe(copy.clearingCacheLabel)
    expect(clearCachesAndReload).toHaveBeenCalledTimes(1)

    await Promise.resolve()

    expect(onReload).toHaveBeenCalledTimes(2)
    expect(logError).not.toHaveBeenCalled()
  })

  it("renders Russian copy when lang is ru", () => {
    document.documentElement.lang = "ru"
    const rootElement = document.createElement("div")
    document.body.append(rootElement)

    const copy = getBootstrapFallbackCopy(document)
    const { container, reloadButton, clearCacheButton } = renderBootstrapFallback({
      documentRef: document,
      rootElement,
      copy,
      logError: vi.fn(),
    })

    expect(copy.title).toBe("Не удалось загрузить приложение")
    expect(container.querySelector("h1")?.textContent).toBe(copy.title)
    expect(container.querySelector("p")?.textContent).toBe(copy.description)
    expect(reloadButton.textContent).toBe("Перезагрузить страницу")
    expect(clearCacheButton.textContent).toBe("Очистить кэш и перезагрузить")
  })
})
