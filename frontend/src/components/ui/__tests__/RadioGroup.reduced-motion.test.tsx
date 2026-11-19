import type { ComponentProps, ReactNode } from "react"
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
  m: {
    span: ({
      initial,
      animate,
      exit,
      transition,
      ...props
    }: ComponentProps<"span"> & {
      initial?: unknown
      animate?: unknown
      exit?: unknown
      transition?: unknown
    }) => (
      <span
        {...props}
        data-testid="radio-indicator"
        data-initial={JSON.stringify(initial)}
        data-animate={JSON.stringify(animate)}
        data-exit={JSON.stringify(exit)}
        data-transition={JSON.stringify(transition)}
      />
    ),
  },
}))

import { RadioGroup, RadioGroupItem } from "../RadioGroup"

function installMotionPreference(initial: boolean) {
  let matches = initial
  const target = new EventTarget()
  const media = Object.assign(target, {
    media: "(prefers-reduced-motion: reduce)",
  })
  Object.defineProperty(media, "matches", { get: () => matches })
  vi.spyOn(window, "matchMedia").mockReturnValue(media as unknown as MediaQueryList)
  return (next: boolean) => {
    matches = next
    const event = new Event("change")
    Object.defineProperty(event, "matches", { value: next })
    act(() => media.dispatchEvent(event))
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function choice(onChange = vi.fn()) {
  return (
    <RadioGroup value="one" name="choice" onChange={onChange} aria-label="Choices">
      <RadioGroupItem value="one" aria-label="One" />
      <RadioGroupItem value="two" aria-label="Two" />
    </RadioGroup>
  )
}

describe("RadioGroup reduced motion", () => {
  it("renders a selected indicator without entrance or exit scaling under reduced motion", () => {
    installMotionPreference(true)
    render(choice())

    const indicator = screen.getByTestId("radio-indicator")
    expect(window.matchMedia).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    expect(indicator).toHaveAttribute("data-initial", "false")
    expect(indicator).toHaveAttribute("data-animate", JSON.stringify({ scale: 1 }))
    expect(indicator).toHaveAttribute("data-exit", JSON.stringify({ scale: 1 }))
    expect(indicator).toHaveAttribute("data-transition", JSON.stringify({ duration: 0 }))
    expect(screen.getByRole("radio", { name: "One" })).toBeChecked()
  })

  it("reacts to preference changes without replacing the focused radio or changing selection", () => {
    const changePreference = installMotionPreference(false)
    const onChange = vi.fn()
    render(choice(onChange))
    const radio = screen.getByRole("radio", { name: "One" })
    const indicator = screen.getByTestId("radio-indicator")
    const spring = JSON.stringify({ type: "spring", stiffness: 500, damping: 30 })
    expect(indicator).toHaveAttribute("data-initial", JSON.stringify({ scale: 0 }))
    expect(indicator).toHaveAttribute("data-transition", spring)
    radio.focus()

    changePreference(true)

    expect(screen.getByRole("radio", { name: "One" })).toBe(radio)
    expect(radio).toHaveFocus()
    expect(radio).toBeChecked()
    expect(indicator).toHaveAttribute("data-transition", JSON.stringify({ duration: 0 }))
    expect(indicator).toHaveAttribute("data-initial", "false")
    expect(indicator).toHaveAttribute("data-exit", JSON.stringify({ scale: 1 }))
    expect(onChange).not.toHaveBeenCalled()

    changePreference(false)

    expect(indicator).toHaveAttribute("data-transition", spring)
    expect(indicator).toHaveAttribute("data-initial", JSON.stringify({ scale: 0 }))
    expect(indicator).toHaveAttribute("data-exit", JSON.stringify({ scale: 0 }))
    expect(radio).toHaveFocus()
    fireEvent.click(screen.getByRole("radio", { name: "Two" }))
    expect(onChange).toHaveBeenCalledExactlyOnceWith(null, "two")
  })
})
