import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react")
  return {
    ...actual,
    // Keep the first render observable: the production effect intentionally
    // synchronizes state after a source change, while these assertions cover
    // the safe initial state before that effect runs.
    useEffect: vi.fn(),
  }
})

import { MediaSlot } from "@/components/ui/MediaSlot"

describe("MediaSlot initial-state mutation contracts", () => {
  it("starts a sourced image loading and without an error fallback", () => {
    render(
      <MediaSlot
        src="https://img.example/initial.jpg"
        alt="Initial image"
        fallback={<span>error fallback</span>}
      />
    )

    const image = screen.getByRole("img", { name: "Initial image" })
    expect(image).toHaveClass("opacity-0")
    expect(image.parentElement?.querySelector(".animate-pulse")).toBeTruthy()
    expect(screen.queryByText("error fallback")).not.toBeInTheDocument()
  })
})
