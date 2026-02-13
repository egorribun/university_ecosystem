import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"

import { ProgressBar } from "@/components/ui/ProgressBar"

describe("ProgressBar", () => {
  it("announces numeric values with the provided aria-label", () => {
    render(<ProgressBar value={30} max={60} ariaLabel="Upload progress" />)

    const progressbar = screen.getByRole("progressbar", { name: "Upload progress" })

    expect(progressbar).toHaveAttribute("aria-valuemin", "0")
    expect(progressbar).toHaveAttribute("aria-valuemax", "60")
    expect(progressbar).toHaveAttribute("aria-valuenow", "30")
  })

  it("omits aria-valuenow when no numeric value is provided", () => {
    render(<ProgressBar ariaLabel="Indeterminate" />)

    const progressbar = screen.getByRole("progressbar", { name: "Indeterminate" })

    expect(progressbar).toHaveAttribute("aria-valuemin", "0")
    expect(progressbar).toHaveAttribute("aria-valuemax", "100")
    expect(progressbar).not.toHaveAttribute("aria-valuenow")
  })
})
