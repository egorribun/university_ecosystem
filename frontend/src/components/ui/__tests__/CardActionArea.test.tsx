import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"

import { CardActionArea } from "@/components/ui/CardActionArea"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

describe("CardActionArea", () => {
  it("renders a type=button by default", async () => {
    await renderWithRouter({
      ui: () => <CardActionArea>Click me</CardActionArea>,
      authProvider: false,
    })
    expect(screen.getByRole("button", { name: "Click me" })).toHaveAttribute("type", "button")
  })

  it("applies the disabled state", async () => {
    await renderWithRouter({
      ui: () => <CardActionArea disabled>Nope</CardActionArea>,
      authProvider: false,
    })
    const btn = screen.getByRole("button")
    expect(btn).toBeDisabled()
    expect(btn.className).toContain("opacity-60")
  })

  it("omits type=button for a non-button `as` (defensive runtime branch)", async () => {
    // The forwardRef wrapper pins `as` to "button" at the type level, so a
    // non-button value is type-unreachable for normal callers. Cast to exercise
    // the runtime `Component !== "button"` branch (typeProps = {}).
    const asAnchor = { as: "a" } as unknown as { as: "button" }
    await renderWithRouter({
      ui: () => <CardActionArea {...asAnchor}>Link-like</CardActionArea>,
      authProvider: false,
    })
    expect(screen.getByRole("button", { name: "Link-like" })).not.toHaveAttribute("type")
  })
})
