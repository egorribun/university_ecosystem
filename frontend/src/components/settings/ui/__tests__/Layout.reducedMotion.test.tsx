import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { withExpectedConsole } from "@/tests/strictConsole"

let Motion: typeof import("framer-motion")
let Layout: typeof import("@/components/settings/ui/Layout")

function createMotionPreference(initial: boolean) {
  let matches = initial
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const query = {
    get matches() {
      return matches
    },
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener)
    }),
    removeEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener)
    }),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  } as unknown as MediaQueryList

  return {
    query,
    listeners,
    set(next: boolean) {
      matches = next
      for (const listener of listeners) listener({ matches } as MediaQueryListEvent)
    },
  }
}

async function advanceFrames(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

function arrow(button: HTMLElement) {
  const svg = button.querySelector("svg")
  if (!svg) throw new Error("Accordion arrow was not rendered")
  return svg
}

function rotation(svg: SVGElement) {
  const match = svg.style.transform.match(/rotate\(([-\d.]+)deg\)/)
  return match ? Number(match[1]) : 0
}

function SelectedTabs() {
  const [selected, setSelected] = useState(0)
  return (
    <Layout.Tabs value={selected} onChange={(_, value) => setSelected(value)}>
      <Layout.Tab label="General" />
      <Layout.Tab label="Security" />
    </Layout.Tabs>
  )
}

beforeAll(async () => {
  // Framer captures requestAnimationFrame during module evaluation.
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(performance.now()), 16)
  )
  vi.stubGlobal("cancelAnimationFrame", (id: number) => window.clearTimeout(id))
  Motion = await import("framer-motion")
  Layout = await import("@/components/settings/ui/Layout")
})

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(async () => {
  cleanup()
  await advanceFrames(1000)
  vi.restoreAllMocks()
  vi.useRealTimers()
})

afterAll(() => {
  vi.unstubAllGlobals()
})

describe("settings layout reduced motion", () => {
  it("snaps the accordion arrow for reduced motion and restores animation when the preference changes", async () => {
    const preference = createMotionPreference(true)
    const matchMedia = vi.spyOn(window, "matchMedia").mockReturnValue(preference.query)
    const view = render(
      <Motion.LazyMotion features={Motion.domAnimation}>
        <Motion.MotionConfig reducedMotion="never">
          <Layout.AccordionSection title="Settings">content</Layout.AccordionSection>
        </Motion.MotionConfig>
      </Motion.LazyMotion>
    )
    const button = screen.getByRole("button", { name: "Settings" })
    fireEvent.click(button)
    await advanceFrames(80)
    expect(button).toHaveAttribute("aria-expanded", "true")
    expect(rotation(arrow(button))).toBe(180)
    expect(matchMedia).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")

    act(() => preference.set(false))
    expect(rotation(arrow(button))).toBe(180)
    fireEvent.click(button)
    await advanceFrames(80)
    expect(rotation(arrow(button))).toBeGreaterThan(0)
    expect(rotation(arrow(button))).toBeLessThan(180)

    act(() => preference.set(true))
    await advanceFrames(80)
    expect(button).toHaveAttribute("aria-expanded", "false")
    expect(rotation(arrow(button))).toBe(0)

    view.unmount()
    expect(preference.listeners.size).toBe(0)
  })

  it("updates the selected tab indicator transition as the preference changes", () => {
    const preference = createMotionPreference(false)
    vi.spyOn(window, "matchMedia").mockReturnValue(preference.query)
    const view = render(
      <Motion.LazyMotion features={Motion.domAnimation}>
        <Motion.MotionConfig reducedMotion="never">
          <SelectedTabs />
        </Motion.MotionConfig>
      </Motion.LazyMotion>
    )
    const tabs = screen.getAllByRole("tab")
    const indicatorTransition = (tab: HTMLElement) => {
      const indicator = tab.querySelector("div")
      if (!indicator) throw new Error("Selected tab indicator was not rendered")
      const visualElement = Motion.visualElementStore.get(indicator)
      if (!visualElement) throw new Error("Indicator has no Framer visual element")
      return visualElement.getProps().transition
    }

    expect(indicatorTransition(tabs[0]!)).toEqual({ type: "spring", bounce: 0.2, duration: 0.6 })
    act(() => preference.set(true))
    fireEvent.click(tabs[1]!)
    expect(tabs[1]).toHaveAttribute("aria-selected", "true")
    expect(indicatorTransition(tabs[1]!)).toEqual({ duration: 0 })

    act(() => preference.set(false))
    fireEvent.click(tabs[0]!)
    expect(tabs[0]).toHaveAttribute("aria-selected", "true")
    expect(indicatorTransition(tabs[0]!)).toEqual({ type: "spring", bounce: 0.2, duration: 0.6 })

    view.unmount()
    expect(preference.listeners.size).toBe(0)
  })

  it("resumes accordion animation after starting with reduced motion in the app provider", async () => {
    const preference = createMotionPreference(true)
    vi.spyOn(window, "matchMedia").mockReturnValue(preference.query)
    await withExpectedConsole("warn", "You have Reduced Motion enabled on your device", () => {
      render(
        <Motion.LazyMotion features={Motion.domAnimation}>
          <Motion.MotionConfig reducedMotion="user">
            <Layout.AccordionSection title="Provider settings">content</Layout.AccordionSection>
          </Motion.MotionConfig>
        </Motion.LazyMotion>
      )
    })
    const button = screen.getByRole("button", { name: "Provider settings" })
    fireEvent.click(button)
    await advanceFrames(80)
    expect(rotation(arrow(button))).toBe(180)

    act(() => preference.set(false))
    fireEvent.click(button)
    await advanceFrames(80)
    expect(rotation(arrow(button))).toBeGreaterThan(0)
    expect(rotation(arrow(button))).toBeLessThan(180)
  })
})
