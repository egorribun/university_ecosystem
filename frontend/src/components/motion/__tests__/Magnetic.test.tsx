import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import Magnetic from "@/components/motion/Magnetic"

describe("Magnetic", () => {
  it("moves relative to its center and returns to rest on pointer leave", () => {
    render(
      <Magnetic strength={0.5} className="magnetic-target">
        Magnetic child
      </Magnetic>
    )
    const target = screen.getByText("Magnetic child")
    expect(target).toHaveStyle({
      transform: "translate3d(0px, 0px, 0)",
      transition: "transform 320ms cubic-bezier(0.34, 1.56, 0.64, 1)",
      willChange: "transform",
    })
    target.getBoundingClientRect = () => ({ left: 10, top: 20, width: 100, height: 80 }) as DOMRect

    fireEvent.mouseMove(target, { clientX: 80, clientY: 90 })
    expect(target).toHaveStyle({ transform: "translate3d(10px, 15px, 0)" })

    fireEvent.mouseLeave(target)
    expect(target).toHaveStyle({ transform: "translate3d(0px, 0px, 0)" })
    expect(target).toHaveClass("magnetic-target")
  })
})
