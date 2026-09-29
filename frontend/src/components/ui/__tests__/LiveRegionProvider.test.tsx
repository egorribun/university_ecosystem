import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { act, renderHook, screen } from "@testing-library/react"

import { renderToString } from "react-dom/server"

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

  it("announces politely when no politeness is given", () => {
    const { result } = renderHook(() => useAnnouncer(), { wrapper })

    act(() => result.current.announce("saved"))

    expect(screen.getByRole("status")).toHaveTextContent("saved")
    expect(screen.getByRole("alert").textContent).toBe("")
  })

  it("restarts the assertive timeout when a newer urgent message arrives", () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useAnnouncer(), { wrapper })

    act(() => result.current.announce("first alert", "assertive"))
    act(() => vi.advanceTimersByTime(2000))
    act(() => result.current.announce("second alert", "assertive"))
    act(() => vi.advanceTimersByTime(1500))

    expect(screen.getByRole("alert")).toHaveTextContent("second alert")
    act(() => vi.advanceTimersByTime(1500))
    expect(screen.getByRole("alert").textContent).toBe("")
  })

  it("renders no live regions in server markup, only the children", () => {
    const html = renderToString(
      <LiveRegionProvider>
        <p>server child</p>
      </LiveRegionProvider>
    )

    expect(html).toContain("server child")
    expect(html).not.toContain("aria-live")
  })
})
