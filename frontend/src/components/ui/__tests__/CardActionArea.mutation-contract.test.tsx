import { createElement, type ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"

const motionState = vi.hoisted(() => ({ calls: [] as Array<Record<string, unknown>> }))

vi.mock("framer-motion", () => ({
  m: {
    button: (props: Record<string, unknown>) => {
      motionState.calls.push(props)
      const {
        children,
        ref: _ref,
        whileHover: _whileHover,
        whileTap: _whileTap,
        ...domProps
      } = props
      return createElement("button", domProps, children as ReactNode)
    },
  },
}))

import { CardActionArea } from "@/components/ui/CardActionArea"
import { EASING } from "@/utils/motion"
import { motion as motionTokens } from "@/theme/tokens"

describe("CardActionArea mutation contract", () => {
  it("preserves the diagnostic display name", () => {
    expect(CardActionArea.displayName).toBe("CardActionArea")
  })

  it("preserves interactive geometry and hover/tap motion options", () => {
    motionState.calls.length = 0

    render(
      <CardActionArea disabled className="card-action-custom" data-testid="card-action">
        Card content
      </CardActionArea>
    )

    const button = screen.getByTestId("card-action")
    expect(button).toHaveClass(
      "group",
      "w-full",
      "focus-visible:ring-2",
      "focus-visible:ring-brand",
      "pointer-events-none",
      "opacity-60",
      "card-action-custom"
    )
    expect(button).toBeDisabled()

    const props = motionState.calls.at(-1)
    expect(props?.whileHover).toEqual({
      y: -4,
      transition: { duration: motionTokens.durationFast, ease: EASING.premium },
    })
    expect(props?.whileTap).toEqual({ scale: 0.98 })
  })
})
