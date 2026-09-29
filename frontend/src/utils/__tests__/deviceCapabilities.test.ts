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

describe("isLowPowerDevice thresholds", () => {
  it("treats exactly 4 GB of memory or 4 CPU cores as constrained", () => {
    expect(isLowPowerDevice({ deviceMemory: 4, hardwareConcurrency: 8 })).toBe(true)
    expect(isLowPowerDevice({ deviceMemory: 8, hardwareConcurrency: 4 })).toBe(true)
  })
})

describe("isLowPowerDevice with non-numeric hints", () => {
  it("ignores null capability hints instead of treating them as zero", () => {
    const nullHints = { deviceMemory: null, hardwareConcurrency: null } as unknown as Parameters<
      typeof isLowPowerDevice
    >[0]
    expect(isLowPowerDevice(nullHints)).toBe(false)
  })

  it("ignores a null memory hint and still evaluates the CPU hint", () => {
    const profile = { deviceMemory: null, hardwareConcurrency: 16 } as unknown as Parameters<
      typeof isLowPowerDevice
    >[0]
    expect(isLowPowerDevice(profile)).toBe(false)
  })
})
