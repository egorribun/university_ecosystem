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

  it("preserves legacy variant classes and gives explicit icons precedence", () => {
    render(
      <div>
        <Button variant="contained" size="small" startIcon={<span data-testid="start" />}>
          contained
        </Button>
        <Button variant="outlined" size="medium" endIcon={<span data-testid="end" />}>
          outlined
        </Button>
        <Button
          variant="text"
          size="large"
          leadingIcon={<span data-testid="leading" />}
          startIcon={<span data-testid="ignored-start" />}
          trailingIcon={<span data-testid="trailing" />}
          endIcon={<span data-testid="ignored-end" />}
        >
          text
        </Button>
      </div>
    )

    const [contained, outlined, text] = screen.getAllByRole("button")
    expect(contained).toHaveClass("bg-linear-brand", "min-h-11")
    expect(outlined).toHaveClass("border", "min-h-12")
    expect(text).toHaveClass("bg-transparent", "min-h-14")
    expect(screen.getByTestId("start")).toBeInTheDocument()
    expect(screen.getByTestId("end")).toBeInTheDocument()
    expect(screen.getByTestId("leading")).toBeInTheDocument()
    expect(screen.getByTestId("trailing")).toBeInTheDocument()
    expect(screen.queryByTestId("ignored-start")).not.toBeInTheDocument()
    expect(screen.queryByTestId("ignored-end")).not.toBeInTheDocument()
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
