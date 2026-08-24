import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Button, fadeDelayStyle, FormControlLabel } from "@/components/settings/ui/Form"

describe("settings Form compatibility wrappers", () => {
  it("builds the typed fade-delay custom property", () => {
    expect(fadeDelayStyle("120ms")).toEqual({ "--fade-delay": "120ms" })
  })

  it("maps all legacy variants and sizes", () => {
    render(
      <div>
        <Button variant="contained" size="small">
          contained
        </Button>
        <Button variant="outlined" size="medium">
          outlined
        </Button>
        <Button variant="text" size="large">
          text
        </Button>
      </div>
    )

    expect(screen.getByRole("button", { name: "contained" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "outlined" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "text" })).toBeInTheDocument()
  })

  it("clones element controls and preserves non-element controls", () => {
    render(
      <div>
        <FormControlLabel value="choice-a" control={<input type="radio" />} label="Choice A" />
        <FormControlLabel value="choice-b" control="raw control" label="Choice B" />
      </div>
    )

    expect(screen.getByRole("radio")).toHaveAttribute("value", "choice-a")
    expect(screen.getByText("raw control")).toBeInTheDocument()
  })
})
