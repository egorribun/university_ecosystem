import { act, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const effectDependencies = vi.hoisted(() => [] as unknown[][])

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react")
  return {
    ...actual,
    useEffect: (effect: () => void | (() => void), dependencies?: readonly unknown[]) => {
      effectDependencies.push(dependencies ? [...dependencies] : [])
      return actual.useEffect(effect, dependencies)
    },
  }
})

import { ClockWidget } from "@/components/dashboard/ClockWidget"

describe("ClockWidget mutation contracts", () => {
  beforeEach(() => {
    effectDependencies.length = 0
    vi.useFakeTimers()
    vi.spyOn(Date.prototype, "toLocaleTimeString").mockReturnValue("10:05")
    vi.spyOn(Date.prototype, "toLocaleDateString").mockReturnValue("Friday, 1 August")
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("installs one stable interval across clock updates and clears it on unmount", async () => {
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval")
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval")
    const view = render(<ClockWidget />)

    expect(setIntervalSpy).toHaveBeenCalledOnce()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000)
    })
    expect(setIntervalSpy).toHaveBeenCalledOnce()
    expect(clearIntervalSpy).not.toHaveBeenCalled()

    const timerHandle = setIntervalSpy.mock.results[0]?.value
    view.unmount()
    expect(clearIntervalSpy).toHaveBeenCalledOnce()
    expect(clearIntervalSpy).toHaveBeenCalledWith(timerHandle)
  })

  it("mounts the interval effect with an empty dependency list", () => {
    render(<ClockWidget />)

    expect(effectDependencies).toContainEqual([])
  })
})
