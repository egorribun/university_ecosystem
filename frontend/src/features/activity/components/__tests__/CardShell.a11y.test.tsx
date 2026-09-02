import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import CardShell from "../CardShell"

describe("CardShell accessibility", () => {
  it("gives labelled statistic cards a semantic group role", () => {
    render(<CardShell aria-label="Attendance statistics">content</CardShell>)

    expect(screen.getByRole("group", { name: "Attendance statistics" })).toBeInTheDocument()
  })
})
