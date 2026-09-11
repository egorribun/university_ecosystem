import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { MediaSlot } from "@/components/ui/MediaSlot"

describe("MediaSlot mutation contracts", () => {
  it("starts a sourced image in a loading state and leaves the image visible", () => {
    render(<MediaSlot src="https://img.example/cover.jpg" alt="Cover image" />)

    const image = screen.getByRole("img", { name: "Cover image" })
    expect(image).toHaveClass(
      "h-full",
      "w-full",
      "object-cover",
      "transition-all",
      "duration-base",
      "opacity-0",
      "group-hover:scale-105"
    )
    expect(screen.getByRole("img").parentElement?.querySelector(".animate-pulse")).toBeTruthy()
  })

  it("removes the loading placeholder after load without requiring a callback", () => {
    const { container } = render(<MediaSlot src="https://img.example/cover.jpg" alt="Cover" />)
    const image = screen.getByRole("img", { name: "Cover" })

    expect(() => fireEvent.load(image)).not.toThrow()
    expect(image).toHaveClass("opacity-100")
    expect(container.querySelector(".animate-pulse")).toBeNull()
  })

  it("renders the error fallback after an error without requiring a callback", () => {
    const { container } = render(
      <MediaSlot
        src="https://img.example/missing.jpg"
        alt="Missing"
        fallback={<span>fallback</span>}
      />
    )
    const image = screen.getByRole("img", { name: "Missing" })

    expect(() => fireEvent.error(image)).not.toThrow()
    expect(screen.getByText("fallback")).toBeInTheDocument()
    expect(container.querySelector("img")).toBeNull()
  })

  it("resets the resource state when the source changes", () => {
    const { rerender } = render(
      <MediaSlot src="https://img.example/first.jpg" alt="First" fallback={<span>fallback</span>} />
    )
    const first = screen.getByRole("img", { name: "First" })
    fireEvent.error(first)
    expect(screen.getByText("fallback")).toBeInTheDocument()

    rerender(
      <MediaSlot
        src="https://img.example/second.jpg"
        alt="Second"
        fallback={<span>fallback</span>}
      />
    )
    expect(screen.getByRole("img", { name: "Second" })).toHaveClass("opacity-0")
    expect(
      screen.getByRole("img", { name: "Second" }).parentElement?.querySelector(".animate-pulse")
    ).toBeTruthy()
  })

  it("keeps the configured aspect ratio, container classes, fallback, and zoom opt-out", () => {
    render(
      <MediaSlot
        aspectRatio="4/3"
        containerClassName="custom-container"
        className="custom-image"
        fallback={<span>empty state</span>}
      />
    )

    const wrapper = screen.getByText("empty state").parentElement
    expect(wrapper).toHaveClass(
      "relative",
      "w-full",
      "overflow-hidden",
      "bg-(--glass-bg)",
      "custom-container"
    )
    expect(wrapper).toHaveStyle({ aspectRatio: "4/3" })

    const { container: sourced } = render(
      <MediaSlot
        src="https://img.example/no-zoom.jpg"
        alt="No zoom"
        hoverZoom={false}
        className="custom-image"
      />
    )
    const image = sourced.querySelector("img")
    expect(image).not.toHaveClass("group-hover:scale-105")
    expect(image).toHaveClass("custom-image", "transition-all", "duration-base")
  })
})
