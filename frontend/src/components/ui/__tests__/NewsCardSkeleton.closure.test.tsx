import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import NewsCardSkeleton from "@/components/ui/NewsCardSkeleton"

describe("NewsCardSkeleton variants", () => {
  it("renders the compact card variant", () => {
    const { container } = render(<NewsCardSkeleton />)
    const article = container.querySelector("article")
    expect(article).toHaveClass("flex-col")
    expect(article).not.toHaveClass("lg:flex-row")
    expect(container.querySelectorAll("[aria-hidden='true']")).toHaveLength(6)
  })

  it("renders the featured card variant with the additional summary line", () => {
    const { container } = render(<NewsCardSkeleton featured />)
    const article = container.querySelector("article")
    expect(article).toHaveClass("lg:flex-row")
    expect(container.querySelectorAll("[aria-hidden='true']")).toHaveLength(7)
  })
})
