import { beforeEach, describe, expect, it, vi } from "vitest"

const preload = vi.hoisted(() => vi.fn(() => Promise.resolve({ default: () => null })))

vi.mock("@/features/map/loadMapLibre", () => ({ loadMapLibre: preload }))

import { Route } from "../_auth/map"

describe("map route preload", () => {
  beforeEach(() => {
    preload.mockReset().mockResolvedValue({ default: () => null })
  })

  it("starts the MapLibre chunk only for an intent preload", async () => {
    const beforeLoad = Route.options.beforeLoad
    expect(beforeLoad).toBeTypeOf("function")

    beforeLoad?.({ cause: "enter" } as never)
    expect(preload).not.toHaveBeenCalled()

    await beforeLoad?.({ cause: "preload" } as never)
    expect(preload).toHaveBeenCalledTimes(1)
  })

  it("absorbs an intent preload failure so route activation can retry", async () => {
    preload.mockRejectedValueOnce(new Error("transient chunk failure"))
    const beforeLoad = Route.options.beforeLoad

    await expect(beforeLoad?.({ cause: "preload" } as never)).resolves.toBeUndefined()
  })
})
