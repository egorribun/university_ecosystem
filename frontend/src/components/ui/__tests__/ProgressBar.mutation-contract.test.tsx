import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ProgressBar } from "@/components/ui/ProgressBar"

describe("ProgressBar mutation contracts", () => {
  it("treats only finite numbers as determinate values", () => {
    const { rerender } = render(<ProgressBar value={50} max={100} ariaLabel="Progress" />)
    const progress = screen.getByRole("progressbar", { name: "Progress" })
    const bar = progress.firstElementChild as HTMLElement

    expect(progress).toHaveAttribute("aria-valuenow", "50")
    expect(bar).toHaveStyle({ width: "50%" })

    rerender(<ProgressBar value={"50" as unknown as number} max={100} ariaLabel="Progress" />)
    expect(progress).not.toHaveAttribute("aria-valuenow")
    expect(bar).toHaveStyle({ width: "0%" })

    rerender(<ProgressBar value={Number.NaN} max={100} ariaLabel="Progress" />)
    expect(progress).not.toHaveAttribute("aria-valuenow")
    expect(bar).toHaveStyle({ width: "0%" })
  })

  it("clamps numeric values, normalizes invalid max, and preserves accessibility options", () => {
    const { rerender } = render(
      <ProgressBar
        value={150}
        max={100}
        liveRegion
        animated={false}
        className="track"
        barClassName="bar"
        ariaLabel="Upload"
      />
    )
    const progress = screen.getByRole("progressbar", { name: "Upload" })
    const bar = progress.firstElementChild as HTMLElement

    expect(progress).toHaveAttribute("aria-valuemax", "100")
    expect(progress).toHaveAttribute("aria-valuenow", "100")
    expect(progress).toHaveAttribute("aria-live", "polite")
    expect(progress).toHaveClass("track")
    expect(bar).toHaveClass("bar")
    expect(bar).toHaveStyle({ width: "100%" })

    rerender(<ProgressBar value={10} max={0} ariaLabel="Upload" />)
    expect(progress).toHaveAttribute("aria-valuemax", "100")
    expect(progress).toHaveAttribute("aria-valuenow", "10")
    expect(bar).toHaveStyle({ width: "10%" })
  })
})
