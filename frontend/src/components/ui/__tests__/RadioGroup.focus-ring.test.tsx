import { LazyMotion, domAnimation } from "framer-motion"
import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { RadioGroup, RadioGroupItem } from "../RadioGroup"

const focusRingSelector = ".peer-focus-visible\\:shadow-focus"
const matchingPeerSelector = ".peer ~ .peer-focus-visible\\:shadow-focus"

describe("RadioGroupItem focus indicator structure", () => {
  it("keeps each labeled radio adjacent to only its own compact peer target", () => {
    render(
      <LazyMotion features={domAnimation}>
        <RadioGroup value="primary" name="delivery" row aria-label="Delivery method">
          <div data-testid="primary-item" className="flex items-center gap-2">
            <RadioGroupItem id="delivery-primary" value="primary" />
            <label htmlFor="delivery-primary">Primary</label>
          </div>
          <div data-testid="secondary-item" className="flex items-center gap-2">
            <RadioGroupItem id="delivery-secondary" value="secondary" />
            <label htmlFor="delivery-secondary">Secondary</label>
          </div>
        </RadioGroup>
      </LazyMotion>
    )

    for (const [itemId, label] of [
      ["primary-item", "Primary"],
      ["secondary-item", "Secondary"],
    ] as const) {
      const item = screen.getByTestId(itemId)
      const radio = within(item).getByRole("radio", { name: label })

      radio.focus()
      expect(radio).toHaveFocus()
      expect(radio).toHaveAccessibleName(label)

      const focusTargets = item.querySelectorAll<HTMLElement>(focusRingSelector)
      expect(focusTargets).toHaveLength(1)
      const focusTarget = focusTargets.item(0)
      expect(focusTarget).toHaveClass("h-6", "w-6", "rounded-full")

      const hitTarget = focusTarget.parentElement
      expect(hitTarget).toHaveClass("relative", "inline-flex", "min-h-11", "min-w-11")
      expect(radio.parentElement).toBe(hitTarget)
      expect(radio.compareDocumentPosition(focusTarget)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)

      // A peer must match only the compact indicator within its own item.
      const matchingTargets = item.querySelectorAll(matchingPeerSelector)
      expect(matchingTargets).toHaveLength(1)
      expect(matchingTargets.item(0)).toBe(focusTarget)
    }
  })
})
