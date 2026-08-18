import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { act, renderHook, screen } from "@testing-library/react"

import { LiveRegionProvider, useAnnouncer } from "@/components/ui/LiveRegionProvider"

const wrapper = ({ children }: { children: ReactNode }) => (
  <LiveRegionProvider>{children}</LiveRegionProvider>
)

describe("LiveRegionProvider / useAnnouncer", () => {
  afterEach(() => vi.useRealTimers())

  it("returns a no-op announcer when used outside the provider", () => {
    const { result } = renderHook(() => useAnnouncer())
    expect(() => result.current.announce("hello")).not.toThrow()
  })

  it("announces polite + assertive messages into the live regions", () => {
    const { result } = renderHook(() => useAnnouncer(), { wrapper })

    act(() => result.current.announce("polite news", "polite"))
    expect(screen.getByRole("status")).toHaveTextContent("polite news")

    act(() => result.current.announce("urgent news", "assertive"))
    expect(screen.getByRole("alert")).toHaveTextContent("urgent news")

    // Re-announcing politely clears the prior timeout + updates the message.
    act(() => result.current.announce("newer", "polite"))
    expect(screen.getByRole("status")).toHaveTextContent("newer")
  })

  it("clears the message after the 3s timeout", () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useAnnouncer(), { wrapper })

    act(() => result.current.announce("temp", "polite"))
    expect(screen.getByRole("status")).toHaveTextContent("temp")

    act(() => vi.advanceTimersByTime(3000))
    expect(screen.getByRole("status").textContent).toBe("")

    act(() => result.current.announce("urgent", "assertive"))
    expect(screen.getByRole("alert")).toHaveTextContent("urgent")
    act(() => vi.advanceTimersByTime(3000))
    expect(screen.getByRole("alert").textContent).toBe("")
  })
})
