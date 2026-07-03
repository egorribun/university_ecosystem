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

  it("uses window.location.href if url is not provided", () => {
    const originalLocation = window.location.href
    Object.defineProperty(window, "location", {
      value: { href: "https://test-location.com/current-page" },
      writable: true,
      configurable: true,
    })

    const { result } = renderHook(() => useShare({ title: "Test" }))
    expect(result.current.shareOptions[0].href).toContain(
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
    let resolveShare!: (value: unknown) => void
    const sharePromise = new Promise((resolve) => {
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
