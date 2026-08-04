import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const { addVersionMock, resolveMediaMock, resolveProxyMock, sanitizeMock } = vi.hoisted(() => ({
  addVersionMock: vi.fn((value: string) => value),
  resolveMediaMock: vi.fn((value: string) => value),
  resolveProxyMock: vi.fn((_value: string, _width?: number) => null as string | null),
  sanitizeMock: vi.fn((value: string) => (value.startsWith("unsafe") ? null : value)),
}))

vi.mock("@/utils/media", () => ({
  addVersionParam: addVersionMock,
  resolveMediaUrl: resolveMediaMock,
  resolveProxyImageUrl: resolveProxyMock,
  sanitizeUrl: sanitizeMock,
}))

import SmartImage from "@/components/media/SmartImage"

describe("SmartImage defensive closure branches", () => {
  it("omits proxy candidates and falls back when the proxy cannot resolve", () => {
    render(<SmartImage srcRaw="/media/unavailable.jpg" fallback="/fallback.png" alt="unavailable" />)
    const image = screen.getByRole("img", { name: "unavailable" })

    expect(image).toHaveAttribute("src", "/fallback.png")
    expect(image).not.toHaveAttribute("srcset")
    expect(resolveProxyMock).toHaveBeenCalled()
  })

  it("rejects an unsafe blob URL before resolving it", () => {
    sanitizeMock.mockImplementation((value: string) => (value.startsWith("blob:") ? null : value))
    render(<SmartImage srcRaw="blob:unsafe" fallback="/fallback.png" alt="unsafe blob" />)
    expect(screen.getByRole("img", { name: "unsafe blob" })).toHaveAttribute("src", "/fallback.png")
  })

  it("omits src when both the computed value and fallback are empty", () => {
    render(<SmartImage srcRaw="/media/empty.jpg" fallback="" alt="empty" />)
    expect(screen.getByRole("img", { name: "empty" })).not.toHaveAttribute("src")
  })

  it("sanitizes an unsafe fallback before assigning it to the image", () => {
    sanitizeMock.mockImplementation((value: string) => (value.startsWith("unsafe") ? null : value))
    render(<SmartImage srcRaw="javascript:alert(1)" fallback="unsafe-fallback" alt="unsafe" />)
    expect(screen.getByRole("img", { name: "unsafe" })).not.toHaveAttribute("src")
  })
})
