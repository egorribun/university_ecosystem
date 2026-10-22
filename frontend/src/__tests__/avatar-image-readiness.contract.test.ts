import { afterEach, describe, expect, it, vi } from "vitest"
import { decodeExistingImage } from "../../tests/e2e-live/avatar-image-readiness"

const imageWithDecode = (
  decode: () => Promise<void>,
  naturalWidth: number,
  naturalHeight: number
): Pick<HTMLImageElement, "decode" | "naturalWidth" | "naturalHeight"> => ({
  decode,
  naturalWidth,
  naturalHeight,
})

describe("existing avatar image decode readiness", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("accepts a resolved responsive image when density-corrected dimensions are zero", async () => {
    const image = imageWithDecode(async () => undefined, 0, 0)

    await expect(decodeExistingImage(image, 50)).resolves.toEqual({
      outcome: "resolved",
      naturalWidth: 0,
      naturalHeight: 0,
    })
  })

  it("reports broken image decode without retaining the browser error", async () => {
    const image = imageWithDecode(
      () => Promise.reject(new Error("private broken-image diagnostic")),
      0,
      0
    )

    const result = await decodeExistingImage(image, 50)

    expect(result).toEqual({
      outcome: "rejected",
      naturalWidth: null,
      naturalHeight: null,
    })
    expect(JSON.stringify(result)).not.toContain("private broken-image diagnostic")
  })

  it("returns a bounded timeout when the existing image decode never settles", async () => {
    vi.useFakeTimers()
    const image = imageWithDecode(() => new Promise<void>(() => undefined), 0, 0)
    const pending = decodeExistingImage(image, 25)

    await vi.advanceTimersByTimeAsync(25)

    await expect(pending).resolves.toEqual({
      outcome: "timeout",
      naturalWidth: null,
      naturalHeight: null,
    })
  })
})
