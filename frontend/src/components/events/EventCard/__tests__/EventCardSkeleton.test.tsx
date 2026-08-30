import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { EventCardSkeleton } from "../EventCardSkeleton"

describe("EventCardSkeleton", () => {
  it("keeps the media placeholder geometry aligned with the rendered event card hero", () => {
    const { container } = render(<EventCardSkeleton />)
    const media = container.querySelector(".skeleton")

    expect(media).toHaveClass("h-48", "sm:h-52")
    expect(media).not.toHaveStyle({ height: "clamp(17.5rem, 50vw, 23.75rem)" })
  })
})
