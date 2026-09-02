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
    expect(image.getAttribute("srcset")).toContain("/api/v1/img/media/photo.jpg?w=320 320w")
    expect(image.getAttribute("srcset")).toContain("/api/v1/img/media/photo.jpg?w=540 540w")
    expect(image).toHaveAttribute(
      "srcset",
      "/api/v1/img/media/photo.jpg?w=320 320w, /api/v1/img/media/photo.jpg?w=540 540w"
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
      "/api/v1/img/media/photo.jpg?w=320 320w, /api/v1/img/media/photo.jpg?w=768 768w"
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
    expect(screen.getByRole("img", { name: "no source" })).not.toHaveAttribute("srcset")
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
})
