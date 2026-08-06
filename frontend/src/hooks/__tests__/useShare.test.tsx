import { renderHook, act } from "@testing-library/react"
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest"
import { useShare } from "../useShare"

describe("useShare", () => {
  const onNotify = vi.fn()
  const translations = {
    shareSuccess: "Success",
    shareError: "Error",
    linkCopied: "Copied",
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()

    // Mock navigator APIs
    Object.defineProperty(navigator, "share", {
      value: vi.fn().mockResolvedValue(undefined),
      configurable: true,
      writable: true,
    })
    Object.defineProperty(navigator, "canShare", {
      value: vi.fn(() => true),
      configurable: true,
      writable: true,
    })
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
      writable: true,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("returns share options based on provided URL", () => {
    const { result } = renderHook(() => useShare({ title: "Test", url: "https://example.com/foo" }))

    expect(result.current.shareOptions).toHaveLength(3)
    const telegram = result.current.shareOptions.find((o) => o.id === "telegram")
    expect(telegram?.href).toContain("https%3A%2F%2Fexample.com%2Ffoo")
    expect(telegram?.href).toContain("text=Test")
  })

  it("uses the translated page title when the explicit title is empty", () => {
    const { result } = renderHook(() =>
      useShare({
        title: "",
        url: "https://example.com/foo",
        translations: { pageTitle: "Translated page" },
      })
    )

    expect(result.current.shareOptions[0]?.href).toContain("text=Translated%20page")
  })

  it("uses native share when available", async () => {
    const { result } = renderHook(() =>
      useShare({ title: "Test Title", url: "https://example.com", onNotify, translations })
    )

    await act(async () => {
      await result.current.handleShare()
    })

    expect(navigator.share).toHaveBeenCalledWith({
      title: "Test Title",
      text: "Test Title",
      url: "https://example.com",
    })
    expect(onNotify).toHaveBeenCalledWith("Success")
    expect(result.current.shareDialogOpen).toBe(false)
  })

  it("opens fallback dialog when native share is unavailable", async () => {
    // @ts-expect-error - navigator.share is read-only in some environments or types
    navigator.share = undefined

    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    await act(async () => {
      await result.current.handleShare()
    })

    expect(result.current.shareDialogOpen).toBe(true)
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("opens the fallback dialog when navigator.canShare rejects the payload", async () => {
    vi.mocked(navigator.canShare).mockReturnValue(false)

    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    await act(async () => {
      await result.current.handleShare()
    })

    expect(result.current.shareDialogOpen).toBe(true)
    expect(navigator.share).not.toHaveBeenCalled()
  })

  it("uses native share when canShare is unavailable and applies default title", async () => {
    Object.defineProperty(navigator, "canShare", {
      value: undefined,
      configurable: true,
      writable: true,
    })

    const { result } = renderHook(() =>
      useShare({ title: "", url: "https://example.com", translations: { pageTitle: "Page" } })
    )

    await act(async () => {
      await result.current.handleShare()
    })

    expect(navigator.share).toHaveBeenCalledWith({
      title: "Page",
      text: "Page",
      url: "https://example.com",
    })
  })

  it("uses the built-in share, notification, and copy fallbacks", async () => {
    const { result } = renderHook(() =>
      useShare({ title: "", url: "https://example.com", onNotify })
    )

    await act(async () => {
      await result.current.handleShare()
    })
    expect(navigator.share).toHaveBeenCalledWith({
      title: "Share",
      text: "Share",
      url: "https://example.com",
    })
    expect(onNotify).toHaveBeenCalledWith("Shared successfully")

    await act(async () => {
      await result.current.handleCopyLink()
    })
    expect(onNotify).toHaveBeenCalledWith("Link copied!")

    vi.mocked(navigator.share).mockRejectedValue(new Error("share failed"))
    await act(async () => {
      await result.current.handleShare()
    })
    expect(onNotify).toHaveBeenCalledWith("Share failed")

    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("copy failed")) },
      configurable: true,
      writable: true,
    })
    await act(async () => {
      await result.current.handleCopyLink()
    })
    expect(onNotify).toHaveBeenCalledWith("Copy failed")
  })

  it("copies link to clipboard and clears state after timeout", async () => {
    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    await act(async () => {
      await result.current.handleCopyLink()
    })

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://example.com")
    expect(result.current.copiedLink).toBe(true)
    expect(onNotify).toHaveBeenCalledWith("Copied")

    act(() => {
      vi.advanceTimersByTime(2200)
    })
    expect(result.current.copiedLink).toBe(false)
  })

  it("handles AbortError in handleShare by doing nothing", async () => {
    vi.mocked(navigator.share).mockRejectedValue({ name: "AbortError" })

    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    await act(async () => {
      await result.current.handleShare()
    })

    expect(onNotify).not.toHaveBeenCalled()
    expect(result.current.sharing).toBe(false)
  })

  it("handles general error in handleShare with notification", async () => {
    vi.mocked(navigator.share).mockRejectedValue(new Error("Boom"))

    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    await act(async () => {
      await result.current.handleShare()
    })

    expect(onNotify).toHaveBeenCalledWith("Error")
  })

  it("handles nameless share failures without requiring a notification callback", async () => {
    vi.mocked(navigator.share).mockRejectedValue({})

    const { result } = renderHook(() => useShare({ title: "Test", url: "https://example.com" }))

    await act(async () => {
      await result.current.handleShare()
    })

    expect(result.current.sharing).toBe(false)
  })

  it("uses window.location.href if url is not provided", () => {
    const originalLocation = window.location.href
    Object.defineProperty(window, "location", {
      value: { href: "https://test-location.com/current-page" },
      writable: true,
      configurable: true,
    })

    const { result } = renderHook(() => useShare({ title: "Test" }))
    expect(result.current.shareOptions[0]!.href).toContain(
      "https%3A%2F%2Ftest-location.com%2Fcurrent-page"
    )

    Object.defineProperty(window, "location", {
      value: { href: originalLocation },
      writable: true,
      configurable: true,
    })
  })

  it("throws error if clipboard API is not available", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
      writable: true,
    })

    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    await act(async () => {
      await result.current.handleCopyLink()
    })

    expect(onNotify).toHaveBeenCalledWith("Error")
  })

  it("reports clipboard write failures with the default error message", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
      configurable: true,
      writable: true,
    })

    const { result } = renderHook(() => useShare({ title: "Test", url: "https://example.com" }))

    await act(async () => {
      await result.current.handleCopyLink()
    })

    expect(result.current.copiedLink).toBe(false)
    expect(result.current.copyingLink).toBe(false)
  })

  it("does not start a second clipboard operation while the first is pending", async () => {
    let resolveCopy!: () => void
    const writeText = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveCopy = resolve
        })
    )
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    })

    const { result } = renderHook(() => useShare({ title: "Test", url: "https://example.com" }))
    let first!: Promise<void>
    act(() => {
      first = result.current.handleCopyLink()
    })
    let second!: Promise<void>
    act(() => {
      second = result.current.handleCopyLink()
    })
    expect(writeText).toHaveBeenCalledOnce()

    await act(async () => {
      resolveCopy()
      await Promise.all([first, second])
    })
  })

  it("returns empty share and copy states when the current location is empty", async () => {
    const originalLocation = window.location
    Object.defineProperty(window, "location", {
      value: { href: "" },
      writable: true,
      configurable: true,
    })

    const { result } = renderHook(() => useShare({ title: "Test" }))
    expect(result.current.shareOptions).toEqual([])
    await act(async () => {
      await result.current.handleShare()
      await result.current.handleCopyLink()
    })
    expect(navigator.share).not.toHaveBeenCalled()

    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
      configurable: true,
    })
  })

  it("throws error in insecure context", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
      writable: true,
    })
    const originalSecure = window.isSecureContext
    Object.defineProperty(window, "isSecureContext", {
      value: false,
      configurable: true,
      writable: true,
    })

    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    await act(async () => {
      await result.current.handleCopyLink()
    })

    expect(onNotify).toHaveBeenCalledWith("Error")

    Object.defineProperty(window, "isSecureContext", {
      value: originalSecure,
      configurable: true,
      writable: true,
    })
  })

  it("clears active copy timeout on subsequent copy", async () => {
    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")

    await act(async () => {
      await result.current.handleCopyLink()
    })
    await act(async () => {
      await result.current.handleCopyLink()
    })

    expect(clearTimeoutSpy).toHaveBeenCalled()
    clearTimeoutSpy.mockRestore()
  })

  it("handleShare returns early if already sharing", async () => {
    let resolveShare!: (value: void | PromiseLike<void>) => void
    const sharePromise = new Promise<void>((resolve) => {
      resolveShare = resolve
    })
    vi.mocked(navigator.share).mockReturnValue(sharePromise)

    const { result } = renderHook(() =>
      useShare({ title: "Test", url: "https://example.com", onNotify, translations })
    )

    // First call sets sharing = true
    let p1!: Promise<void>
    act(() => {
      p1 = result.current.handleShare()
    })

    // Second call should return early
    let p2!: Promise<void>
    act(() => {
      p2 = result.current.handleShare()
    })

    // Resolve the first share
    await act(async () => {
      resolveShare(undefined)
      await Promise.all([p1, p2])
    })

    expect(navigator.share).toHaveBeenCalledTimes(1)
  })
})
