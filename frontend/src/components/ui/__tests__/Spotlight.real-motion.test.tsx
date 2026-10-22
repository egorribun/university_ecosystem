import { fireEvent, render, waitFor } from "@testing-library/react"
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest"

// Motion captures requestAnimationFrame when its frame batcher is evaluated.
let Motion!: typeof import("framer-motion")
let Spotlight!: typeof import("@/components/ui/Spotlight").Spotlight

beforeAll(async () => {
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(window.performance.now()), 16)
  )
  vi.stubGlobal("cancelAnimationFrame", (id: number) => window.clearTimeout(id))

  Motion = await import("framer-motion")
  ;({ Spotlight } = await import("@/components/ui/Spotlight"))
})

afterEach(() => {
  vi.restoreAllMocks()
})

afterAll(() => {
  vi.unstubAllGlobals()
})

describe("Spotlight with real Framer Motion", () => {
  it("updates numeric gradient coordinates after actual wrapper mouse moves", async () => {
    const { container } = render(
      <Motion.LazyMotion features={Motion.domAnimation}>
        <Spotlight className="spotlight-real-motion-regression">
          <span>Spotlight content</span>
        </Spotlight>
      </Motion.LazyMotion>
    )

    const wrapper = container.querySelector<HTMLDivElement>(".spotlight-real-motion-regression")
    if (!wrapper) throw new Error("Spotlight wrapper was not rendered")
    const overlay = wrapper.querySelector<HTMLDivElement>(".pointer-events-none")
    if (!overlay) throw new Error("Spotlight overlay was not rendered")

    const bounds: DOMRect = {
      x: 11,
      y: 17,
      left: 11,
      top: 17,
      right: 311,
      bottom: 217,
      width: 300,
      height: 200,
      toJSON: () => ({}),
    }
    const getBounds = vi.spyOn(wrapper, "getBoundingClientRect").mockReturnValue(bounds)
    const expectGradientAt = (x: number, y: number) => {
      const background = overlay.style.background.toLowerCase().replace(/\s+/g, " ")
      expect(background).toContain("radial-gradient")
      expect(background).toContain(`circle at ${x}px ${y}px`)
      expect(background).not.toContain("[object object]")
    }

    // Prove the actual component receives the event before checking the outcome.
    fireEvent.mouseMove(wrapper, { clientX: 41, clientY: 67 })
    expect(getBounds).toHaveBeenCalledTimes(1)
    await waitFor(() => expectGradientAt(30, 50))

    // A later position must update the same overlay, not a new render.
    fireEvent.mouseMove(wrapper, { clientX: 101, clientY: 117 })
    expect(getBounds).toHaveBeenCalledTimes(2)
    await waitFor(() => expectGradientAt(90, 100))
  })
})
