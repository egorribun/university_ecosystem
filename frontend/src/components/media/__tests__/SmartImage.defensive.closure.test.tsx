import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

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

beforeEach(() => {
  addVersionMock.mockReset().mockImplementation((value: string) => value)
  resolveMediaMock.mockReset().mockImplementation((value: string) => value)
  resolveProxyMock.mockReset().mockImplementation(() => null)
  sanitizeMock
    .mockReset()
    .mockImplementation((value: string) => (value.startsWith("unsafe") ? null : value))
})

describe("SmartImage defensive closure branches", () => {
  it("omits proxy candidates and falls back when the proxy cannot resolve", () => {
    render(
      <SmartImage srcRaw="/media/unavailable.jpg" fallback="/fallback.png" alt="unavailable" />
    )
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

  it("does not build responsive candidates for an unsafe source", () => {
    resolveProxyMock.mockImplementation((_value: string, width?: number) =>
      width ? `/proxy/image?w=${width}` : "/proxy/image"
    )

    render(
      <SmartImage
        srcRaw="unsafe-image"
        responsiveWidths={[320]}
        fallback="unsafe-fallback"
        alt="unsafe source"
      />
    )

    const image = screen.getByRole("img", { name: "unsafe source" })
    expect(image).not.toHaveAttribute("src")
    expect(image).not.toHaveAttribute("srcset")
    expect(sanitizeMock).toHaveBeenCalledWith("unsafe-image")
  })

  it("returns the built-in fallback and default sizes when props omit them", () => {
    resolveProxyMock.mockImplementation((_value: string, width?: number) =>
      width ? `/proxy/image?w=${width}` : "/proxy/image"
    )
    render(<SmartImage srcRaw="unsafe-image" responsiveWidths={[320]} alt="default" />)

    const image = screen.getByRole("img", { name: "default" })
    expect(image).toHaveAttribute("src", "/fallbacks/placeholder.png")

    render(<SmartImage srcRaw="/media/photo.jpg" responsiveWidths={[320]} alt="sized" />)
    expect(screen.getByRole("img", { name: "sized" })).toHaveAttribute(
      "sizes",
      "(max-width: 45rem) 82vw, 28.75rem"
    )

    render(<SmartImage srcRaw="unsafe-image" fallback="/fallback.png" />)
    expect(document.querySelector('img[alt=""]')).not.toBeNull()
  })

  it("keeps blob previews unchanged even when a cache version is supplied", () => {
    render(
      <SmartImage
        srcRaw="blob:http://localhost/preview"
        cacheV="v1"
        fallback="/fallback.png"
        alt="blob preview"
      />
    )

    const image = screen.getByRole("img", { name: "blob preview" })
    expect(image).toHaveAttribute("src", "blob:http://localhost/preview")
    expect(resolveProxyMock).not.toHaveBeenCalled()
    expect(addVersionMock).not.toHaveBeenCalled()
  })

  it("does not version an image when the proxy cannot resolve it", () => {
    addVersionMock.mockImplementation(() => "/unexpected-versioned-image")
    resolveProxyMock.mockReturnValue(null)

    render(<SmartImage srcRaw="/media/unavailable.jpg" cacheV="v1" alt="unresolved" />)

    const image = screen.getByRole("img", { name: "unresolved" })
    expect(image).toHaveAttribute("src", "/fallbacks/placeholder.png")
    expect(addVersionMock).not.toHaveBeenCalled()
  })
})
