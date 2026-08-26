import { describe, expect, it, vi } from "vitest"
import { isLowPowerDevice } from "@/utils/deviceCapabilities"

describe("isLowPowerDevice", () => {
  it("honours reduced-data connections", () => {
    expect(isLowPowerDevice({ connection: { saveData: true } })).toBe(true)
  })

  it("detects constrained memory or CPU profiles", () => {
    expect(isLowPowerDevice({ deviceMemory: 2, hardwareConcurrency: 8 })).toBe(true)
    expect(isLowPowerDevice({ deviceMemory: 8, hardwareConcurrency: 2 })).toBe(true)
  })

  it("keeps effects on for capable and unknown profiles", () => {
    expect(isLowPowerDevice({ deviceMemory: 8, hardwareConcurrency: 8 })).toBe(false)
    expect(isLowPowerDevice({})).toBe(false)
  })

  it("defaults to the live browser profile and stays safe during server rendering", () => {
    vi.stubGlobal("navigator", { deviceMemory: 2, hardwareConcurrency: 8 })
    expect(isLowPowerDevice()).toBe(true)

    vi.stubGlobal("navigator", undefined)
    expect(isLowPowerDevice()).toBe(false)
    vi.unstubAllGlobals()
  })
})
