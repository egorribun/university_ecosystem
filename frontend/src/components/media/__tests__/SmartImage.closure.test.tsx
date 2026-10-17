import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import SmartImage from "@/components/media/SmartImage"

describe("SmartImage defensive and responsive branches", () => {
  it("uses the media proxy and deduplicated positive responsive widths", () => {
    render(
      <SmartImage
        srcRaw="/media/photo.jpg"
        cacheV="v2"
        responsiveWidths={[0, -1, 540, 320, 540, Number.NaN]}
        alt="photo"
      />
    )

    const image = screen.getByRole("img", { name: "photo" })
    expect(image.getAttribute("src")).toContain("/api/v1/img/media/photo.jpg?_v=v2")
    expect(image.getAttribute("srcset")).toContain("/api/v1/img/media/photo.jpg?w=320&_v=v2 320w")
    expect(image.getAttribute("srcset")).toContain("/api/v1/img/media/photo.jpg?w=540&_v=v2 540w")
    expect(image).toHaveAttribute(
      "srcset",
      "/api/v1/img/media/photo.jpg?w=320&_v=v2 320w, /api/v1/img/media/photo.jpg?w=540&_v=v2 540w"
    )
    expect(image).toHaveAttribute("loading", "lazy")
    expect(image).toHaveStyle({ objectFit: "cover" })
  })

  it("keeps safe blob URLs unchanged and omits srcSet", () => {
    render(<SmartImage srcRaw="blob:http://localhost/preview" alt="preview" />)
    const image = screen.getByRole("img", { name: "preview" })
    expect(image).toHaveAttribute("src", "blob:http://localhost/preview")
    expect(image).not.toHaveAttribute("srcset")
    expect(image).not.toHaveAttribute("sizes")
  })

  it("falls back for invalid sources and after an image error", () => {
    const onError = vi.fn()
    render(<SmartImage srcRaw="javascript:alert(1)" fallback="/fallback.png" onError={onError} />)
    const image = document.querySelector("img") as HTMLImageElement
    expect(image.getAttribute("src")).toContain("/fallback.png")

    fireEvent.error(image)
    expect(onError).toHaveBeenCalledOnce()
    expect(image.getAttribute("src")).toContain("/fallback.png")
    fireEvent.error(image)
    expect(onError).toHaveBeenCalledTimes(2)
  })

  it("recomputes versioned sources and responsive candidates after rerender", () => {
    const { rerender } = render(
      <SmartImage srcRaw="/media/photo.jpg" cacheV="first" alt="versioned" />
    )
    const image = screen.getByRole("img", { name: "versioned" })
    expect(image).toHaveAttribute(
      "src",
      "http://localhost:3000/api/v1/img/media/photo.jpg?_v=first"
    )

    rerender(
      <SmartImage
        srcRaw="/media/photo.jpg"
        cacheV="second"
        responsiveWidths={[768, 320]}
        alt="versioned"
      />
    )
    expect(image).toHaveAttribute(
      "src",
      "http://localhost:3000/api/v1/img/media/photo.jpg?_v=second"
    )
    expect(image).toHaveAttribute(
      "srcset",
      "/api/v1/img/media/photo.jpg?w=320&_v=second 320w, /api/v1/img/media/photo.jpg?w=768&_v=second 768w"
    )
  })

  it("does not throw when optional image callbacks are absent", () => {
    render(<SmartImage srcRaw="/media/photo.jpg" alt="without callbacks" />)
    const image = screen.getByRole("img", { name: "without callbacks" })

    fireEvent.load(image)
    fireEvent.error(image)
    fireEvent.error(image)
    expect(image).toHaveAttribute("src", "http://localhost:3000/fallbacks/placeholder.png")
  })

  it("omits srcSet when responsive widths are empty or the source is absent", () => {
    const { rerender } = render(
      <SmartImage srcRaw="/media/photo.jpg" responsiveWidths={[]} alt="empty widths" />
    )
    expect(screen.getByRole("img", { name: "empty widths" })).not.toHaveAttribute("srcset")
    expect(screen.getByRole("img", { name: "empty widths" })).not.toHaveAttribute("sizes")

    rerender(<SmartImage fallback="/fallback.png" alt="no source" />)
    const image = screen.getByRole("img", { name: "no source" })
    expect(image.getAttribute("src")).toContain("/fallback.png")
    expect(image).not.toHaveAttribute("srcset")
  })

  it("forwards load callbacks and caller style/attributes", () => {
    const onLoad = vi.fn()
    render(
      <SmartImage
        srcRaw="https://cdn.example/image.jpg"
        alt="remote"
        onLoad={onLoad}
        style={{ objectFit: "contain" }}
        data-testid="remote-image"
        loading="eager"
      />
    )
    const image = screen.getByTestId("remote-image")
    fireEvent.load(image)
    expect(onLoad).toHaveBeenCalledOnce()
    expect(image).toHaveAttribute("loading", "eager")
    expect(image).toHaveStyle({ objectFit: "contain" })
  })

  it("versions each responsive candidate with the primary avatar", () => {
    render(
      <SmartImage
        srcRaw="/media/avatar.png"
        cacheV="profile-r7"
        responsiveWidths={[64, 96]}
        alt="account avatar"
      />
    )

    const image = screen.getByRole("img", { name: "account avatar" })
    const primary = new URL(image.getAttribute("src") ?? "", window.location.origin)
    const candidates = (image.getAttribute("srcset") ?? "").split(",").map((entry) => {
      const [url, width] = entry.trim().split(/\s+/u)
      return { url: new URL(url ?? "", window.location.origin), width }
    })

    expect(primary.searchParams.get("_v")).toBe("profile-r7")
    expect(candidates.map(({ url }) => url.searchParams.get("_v"))).toEqual([
      "profile-r7",
      "profile-r7",
    ])
    expect(candidates.map(({ url }) => url.searchParams.get("w"))).toEqual(["64", "96"])
    expect(candidates.map(({ width }) => width)).toEqual(["64w", "96w"])
  })

  it("drops responsive candidates on fallback and preserves caller props", () => {
    const onError = vi.fn()
    render(
      <SmartImage
        srcRaw="/media/unavailable.png"
        cacheV="profile-r1"
        responsiveWidths={[64]}
        fallback="/avatar-fallback.png"
        alt="account avatar"
        onError={onError}
        data-testid="avatar-image"
      />
    )

    const image = screen.getByTestId("avatar-image")
    expect(image).toHaveAttribute("srcset")
    expect(image).toHaveAttribute("sizes")
    fireEvent.error(image)

    expect(new URL(image.getAttribute("src") ?? "", window.location.origin).pathname).toBe(
      "/avatar-fallback.png"
    )
    expect(image).not.toHaveAttribute("srcset")
    expect(image).not.toHaveAttribute("sizes")
    expect(image).toHaveAttribute("alt", "account avatar")
    expect(image).toHaveAttribute("data-testid", "avatar-image")
    expect(onError).toHaveBeenCalledOnce()

    fireEvent.error(image)
    expect(image).not.toHaveAttribute("srcset")
    expect(onError).toHaveBeenCalledTimes(2)
  })

  it("retries the primary image immediately when srcRaw changes after failure", () => {
    const { rerender } = render(
      <SmartImage
        srcRaw="/media/unavailable.png"
        cacheV="profile-r1"
        responsiveWidths={[64]}
        fallback="/avatar-fallback.png"
        alt="account avatar"
      />
    )
    const image = screen.getByRole("img", { name: "account avatar" })
    fireEvent.error(image)

    rerender(
      <SmartImage
        srcRaw="/media/new-avatar.png"
        cacheV="profile-r1"
        responsiveWidths={[64]}
        fallback="/avatar-fallback.png"
        alt="account avatar"
      />
    )

    const primary = new URL(image.getAttribute("src") ?? "", window.location.origin)
    const candidate = new URL(
      (image.getAttribute("srcset") ?? "").split(/\s+/u)[0] ?? "",
      window.location.origin
    )
    expect(primary.pathname).toBe("/api/v1/img/media/new-avatar.png")
    expect(primary.searchParams.get("_v")).toBe("profile-r1")
    expect(candidate.pathname).toBe("/api/v1/img/media/new-avatar.png")
    expect(candidate.searchParams.get("_v")).toBe("profile-r1")
    expect(candidate.searchParams.get("w")).toBe("64")
  })

  it("retries the primary image immediately when cacheV changes after failure", () => {
    const { rerender } = render(
      <SmartImage
        srcRaw="/media/unavailable.png"
        cacheV="profile-r1"
        responsiveWidths={[64]}
        fallback="/avatar-fallback.png"
        alt="account avatar"
      />
    )
    const image = screen.getByRole("img", { name: "account avatar" })
    fireEvent.error(image)

    rerender(
      <SmartImage
        srcRaw="/media/unavailable.png"
        cacheV="profile-r2"
        responsiveWidths={[64]}
        fallback="/avatar-fallback.png"
        alt="account avatar"
      />
    )

    const primary = new URL(image.getAttribute("src") ?? "", window.location.origin)
    const candidate = new URL(
      (image.getAttribute("srcset") ?? "").split(/\s+/u)[0] ?? "",
      window.location.origin
    )
    expect(primary.pathname).toBe("/api/v1/img/media/unavailable.png")
    expect(primary.searchParams.get("_v")).toBe("profile-r2")
    expect(candidate.pathname).toBe("/api/v1/img/media/unavailable.png")
    expect(candidate.searchParams.get("_v")).toBe("profile-r2")
    expect(candidate.searchParams.get("w")).toBe("64")
  })
})
