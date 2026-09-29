import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"

import { Tooltip } from "@/components/ui/Tooltip"

describe("Tooltip", () => {
  it("applies title and describedby when given string content", () => {
    render(
      <Tooltip content="Helpful hint">
        <button type="button">Trigger</button>
      </Tooltip>
    )

    const trigger = screen.getByRole("button", { name: "Trigger" })
    const tooltipId = trigger.getAttribute("aria-describedby")

    expect(trigger).toHaveAttribute("title", "Helpful hint")
    expect(tooltipId).toBeTruthy()
    const liveTooltip = tooltipId ? document.getElementById(tooltipId) : null
    expect(liveTooltip).toHaveAttribute("role", "tooltip")
    expect(liveTooltip).toHaveTextContent("Helpful hint")
    expect(liveTooltip).toHaveClass("sr-only")
  })

  it("renders sr-only tooltip content when React nodes are provided", () => {
    render(
      <Tooltip content={<span>Screen reader only</span>}>
        <button type="button">Opener</button>
      </Tooltip>
    )

    const trigger = screen.getByRole("button", { name: "Opener" })
    const tooltipId = trigger.getAttribute("aria-describedby")

    expect(tooltipId).toBeTruthy()

    const liveTooltip = tooltipId ? document.getElementById(tooltipId) : null
    expect(liveTooltip).not.toBeNull()
    expect(liveTooltip).toHaveAttribute("role", "tooltip")
    expect(liveTooltip).toHaveTextContent("Screen reader only")
    // The Tailwind tooltip surfaces non-string content via an sr-only span so screen
    // readers can pick up rich descriptions even without a browser tooltip.
    expect(liveTooltip).toHaveClass("sr-only")
  })

  it("does not pass an empty title prop for rich tooltip content", () => {
    const PropProbe = (props: { title?: string }) => (
      <output data-testid="title-prop-present">
        {Object.prototype.hasOwnProperty.call(props, "title") ? "present" : "absent"}
      </output>
    )

    render(
      <Tooltip content={<span>Rich hint</span>}>
        <PropProbe />
      </Tooltip>
    )

    expect(screen.getByTestId("title-prop-present")).toHaveTextContent("absent")
  })

  it("keeps the wrapper's inline-flex contract", () => {
    const { container } = render(
      <Tooltip content="Helpful hint">
        <button type="button">Trigger</button>
      </Tooltip>
    )

    expect(container.firstElementChild).toHaveClass("inline-flex")
  })

  it("keeps the stable component display name", () => {
    expect(Tooltip.displayName).toBe("Tooltip")
  })
})
