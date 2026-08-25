import { describe, expect, it, vi } from "vitest"

const sharedMock = vi.fn()

describe("Vitest mock isolation", () => {
  it("records calls made by the current test", () => {
    sharedMock("current-test")

    expect(sharedMock).toHaveBeenCalledOnce()
  })

  it("starts the next test with an empty call history", () => {
    expect(sharedMock).not.toHaveBeenCalled()
  })
})
