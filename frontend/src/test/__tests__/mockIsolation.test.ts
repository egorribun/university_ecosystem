import { describe, expect, it, vi } from "vitest"

import vitestConfig from "../../../vitest.config"

const sharedMock = vi.fn()

describe("Vitest mock isolation", () => {
  it("is enabled by the canonical Vitest configuration", () => {
    expect(vitestConfig.test?.clearMocks).toBe(true)
  })

  it("records calls made by the current test", () => {
    sharedMock("current-test")

    expect(sharedMock).toHaveBeenCalledOnce()
  })

  it("starts the next test with an empty call history", () => {
    expect(sharedMock).not.toHaveBeenCalled()
  })
})
