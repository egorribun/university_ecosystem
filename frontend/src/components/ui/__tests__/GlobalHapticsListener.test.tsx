import { describe, expect, it, vi } from "vitest"
import { render, fireEvent } from "@testing-library/react"
import { GlobalHapticsListener } from "../GlobalHapticsListener"
import React from "react"

const mockTrigger = vi.fn()
vi.mock("@/hooks/useHaptics", () => ({
  useHaptics: () => ({
    trigger: mockTrigger,
  }),
}))

describe("GlobalHapticsListener component", () => {
  it("triggers haptics on click of element with data-haptic", () => {
    render(
      <>
        <GlobalHapticsListener />
        <button data-testid="btn" data-haptic="light">Click me</button>
        <button data-testid="btn-no-haptic">No haptic</button>
      </>
    )

    fireEvent.click(document.getElementById("btn-no-haptic") || document.body)
    expect(mockTrigger).not.toHaveBeenCalled()

    const btn = document.querySelector("[data-testid='btn']")
    expect(btn).toBeDefined()
    if (btn) {
      fireEvent.click(btn)
      expect(mockTrigger).toHaveBeenCalledWith("light")
    }
  })
})
