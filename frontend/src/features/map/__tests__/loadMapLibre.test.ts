import { beforeEach, describe, expect, it, vi } from "vitest"

const mockState = vi.hoisted(() => ({ attempts: 0 }))

describe("loadMapLibre", () => {
  beforeEach(() => {
    mockState.attempts = 0
    vi.resetModules()
    vi.doUnmock("@/components/map/MapLibreMap")
  })

  it("deduplicates concurrent intent preloads", async () => {
    vi.doMock("@/components/map/MapLibreMap", () => ({ default: () => null }))
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")
    const first = loadMapLibre()
    const second = loadMapLibre()

    expect(second).toBe(first)
    await expect(first).resolves.toHaveProperty("default")
  })

  it("allows a later route activation to retry a failed chunk load", async () => {
    vi.doMock("@/components/map/MapLibreMap", () => {
      mockState.attempts += 1
      if (mockState.attempts === 1) throw new Error("transient chunk failure")
      return { default: () => null }
    })
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")

    await expect(loadMapLibre()).rejects.toThrow()
    await expect(loadMapLibre()).resolves.toHaveProperty("default")
    expect(mockState.attempts).toBe(2)
  })
})
