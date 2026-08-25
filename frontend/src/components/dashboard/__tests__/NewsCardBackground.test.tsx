import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { NewsCardBackground } from "@/components/dashboard/NewsCardBackground"

describe("NewsCardBackground", () => {
  it("renders one static category wash without blur or perpetual animation", () => {
    const { container } = render(<NewsCardBackground />)

    expect(container.querySelectorAll("[aria-hidden='true']")).toHaveLength(1)
    expect(container.querySelector('[style*="animation"]')).toBeNull()
    expect(container.querySelector('[class*="blur"]')).toBeNull()
  })
})
