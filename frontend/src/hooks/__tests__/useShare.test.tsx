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
    const { result } = renderHook(() => 
      useShare({ title: "Test", url: "https://example.com/foo" })
    )
    
    expect(result.current.shareOptions).toHaveLength(3)
    const telegram = result.current.shareOptions.find(o => o.id === "telegram")
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
    // @ts-ignore
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
})
