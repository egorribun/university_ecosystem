import { fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

// Motion captures requestAnimationFrame when its frame batcher is evaluated.
// Use jsdom's native frame scheduler, whose callbacks are cancelled when the
// environment closes. In Vitest, window.setTimeout is a Node-owned timer.
let Motion!: typeof import("framer-motion")
let Spotlight!: typeof import("@/components/ui/Spotlight").Spotlight

beforeAll(async () => {
  Motion = await import("framer-motion")
  ;({ Spotlight } = await import("@/components/ui/Spotlight"))
})

afterEach(() => {
  vi.restoreAllMocks()
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

  it("cancels pending gradient writes when the wrapper unmounts", async () => {
    const { container, unmount } = render(
      <Motion.LazyMotion features={Motion.domAnimation}>
        <Spotlight className="spotlight-unmount-regression" />
      </Motion.LazyMotion>
    )
    const wrapper = container.querySelector<HTMLDivElement>(".spotlight-unmount-regression")
    const overlay = wrapper?.querySelector<HTMLDivElement>(".pointer-events-none")
    if (!wrapper || !overlay) throw new Error("Spotlight was not rendered")
    const backgroundWrite = vi.spyOn(overlay.style, "background", "set")

    fireEvent.mouseMove(wrapper, { clientX: 41, clientY: 67 })
    unmount()
    // Let the shared Motion batch run, including any next-frame follow-up.
    // Component work must be cancelled, even if the scheduler itself is awake.
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    })
    expect(backgroundWrite).not.toHaveBeenCalled()
  })
})
