import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Skeleton } from "@/components/ui/Skeleton"

describe("Skeleton", () => {
  it("is a busy decorative placeholder by default without creating a live region", () => {
    const { container } = render(<Skeleton />)
    const skeleton = container.firstElementChild

    expect(skeleton).toHaveAttribute("aria-busy", "true")
    expect(skeleton).toHaveAttribute("aria-hidden", "true")
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("exposes one labelled polite status when an aria label is supplied", () => {
    render(<Skeleton ariaLabel="Loading profile" aria-busy="false" />)
    const status = screen.getByRole("status", { name: "Loading profile" })

    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(status).not.toHaveAttribute("aria-hidden")
  })
})

describe("Skeleton rounding", () => {
  const renderSkeleton = (props: Parameters<typeof Skeleton>[0]) => {
    const { container, unmount } = render(<Skeleton {...props} />)
    const node = container.firstElementChild as HTMLElement
    const rendered = { className: node.className, borderRadius: node.style.borderRadius }
    unmount()
    return rendered
  }

  it("is rounded by default, exactly like an explicit rounded skeleton", () => {
    const byDefault = renderSkeleton({})
    const rounded = renderSkeleton({ rounded: true })
    const square = renderSkeleton({ rounded: false })

    expect(byDefault).toEqual(rounded)
    expect(byDefault.className).not.toBe(square.className)
    expect(byDefault.borderRadius).toBe("")
  })

  it.each([
    ["full", "rounded-full"],
    ["sm", "rounded-(--radius-sm)"],
    ["md", "rounded-(--radius-md)"],
    ["lg", "rounded-(--radius-lg)"],
    ["xl", "rounded-(--radius-xl)"],
  ] as const)(
    "maps the %s radius token to its design class without an inline radius",
    (rounded, radiusClass) => {
      const { container } = render(<Skeleton rounded={rounded} />)
      const node = container.firstElementChild as HTMLElement

      expect(node).toHaveClass(radiusClass)
      expect(node).not.toHaveClass("rounded-none")
      expect(node.style.borderRadius).toBe("")
    }
  )

  it.each(["7px", "50%", "0.75rem"])(
    "applies custom CSS radius %s inline and disables the token radius",
    (rounded) => {
      const { container } = render(<Skeleton rounded={rounded} />)
      const node = container.firstElementChild as HTMLElement

      expect(node).toHaveClass("rounded-none")
      expect(node).not.toHaveClass("rounded-(--radius-md)")
      expect(node.style.borderRadius).toBe(rounded)
    }
  )

  it("falls back to customRounding when no custom radius string is given", () => {
    expect(renderSkeleton({ rounded: true, customRounding: "3px" }).borderRadius).toBe("3px")
    expect(renderSkeleton({ rounded: "9px", customRounding: "3px" }).borderRadius).toBe("9px")
  })

  it("allows explicit style to override both custom radius inputs", () => {
    expect(
      renderSkeleton({ rounded: "9px", customRounding: "3px", style: { borderRadius: "5px" } })
        .borderRadius
    ).toBe("5px")
  })

  it("exposes a diagnostic display name", () => {
    expect(Skeleton.displayName).toBe("Skeleton")
  })
})
