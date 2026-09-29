import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { mockJsPDF, mockLogError, mockToPng } = vi.hoisted(() => ({
  mockJsPDF: vi.fn(),
  mockLogError: vi.fn(),
  mockToPng: vi.fn(),
}))

vi.mock("html-to-image", () => ({ toPng: mockToPng }))
vi.mock("jspdf", () => ({ jsPDF: mockJsPDF }))
vi.mock("@/app/logger", () => ({ logError: mockLogError }))

import { exportActivityAsPdf, exportActivityAsPng } from "../activityExport"

const pdf = {
  internal: {
    pageSize: {
      getWidth: vi.fn(() => 210),
      getHeight: vi.fn(() => 297),
    },
  },
  setFontSize: vi.fn(),
  text: vi.fn(),
  addImage: vi.fn(),
  save: vi.fn(),
}

const setImageBehavior = (behavior: "load" | "error" | "timeout", width = 800, height = 600) => {
  class FakeImage {
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    src = ""

    constructor() {
      if (behavior === "load") setTimeout(() => this.onload?.(), 0)
      if (behavior === "error") setTimeout(() => this.onerror?.(), 0)
    }

    readonly width = width
    readonly height = height
  }
  vi.stubGlobal("Image", FakeImage)
}

/** Image whose load settles in a microtask, so no timer other than the guard runs. */
const stubMicrotaskImage = (width: number, height: number, outcome: "load" | "error" = "load") => {
  class FakeImage {
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    readonly width = width
    readonly height = height
    set src(_value: string) {
      queueMicrotask(() => (outcome === "load" ? this.onload?.() : this.onerror?.()))
    }
  }
  vi.stubGlobal("Image", FakeImage)
}

beforeEach(() => {
  mockToPng.mockReset()
  mockToPng.mockResolvedValue("data:image/png;base64,test")
  mockLogError.mockReset()
  mockJsPDF.mockReset()
  mockJsPDF.mockImplementation(function MockJsPdf(this: typeof pdf) {
    Object.assign(this, pdf)
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("activityExport closure", () => {
  it("creates a portrait PDF and saves it with the requested metadata", async () => {
    setImageBehavior("load", 600, 800)
    const result = await exportActivityAsPdf(document.createElement("section"), "Activity", "x.pdf")

    expect(result).toEqual({ success: true })
    expect(mockJsPDF).toHaveBeenCalledWith(expect.objectContaining({ orientation: "portrait" }))
    expect(pdf.save).toHaveBeenCalledWith("x.pdf")
    expect(pdf.text).toHaveBeenCalledWith("Activity", 10, 12)
  })

  it("returns a structured PNG error when html-to-image rejects", async () => {
    mockToPng.mockRejectedValueOnce(new Error("png unavailable"))
    const result = await exportActivityAsPng(document.createElement("section"))

    expect(result).toEqual({ success: false, error: "png unavailable" })
    expect(mockLogError).toHaveBeenCalledWith(
      "[activityExport] PNG export failed:",
      "png unavailable"
    )
  })

  it("uses the generic PNG error for a non-Error rejection", async () => {
    mockToPng.mockRejectedValueOnce("png unavailable")

    await expect(exportActivityAsPng(document.createElement("section"))).resolves.toEqual({
      success: false,
      error: "PNG export failed",
    })
  })

  it("returns a structured PDF error when the image cannot load", async () => {
    setImageBehavior("error")
    const result = await exportActivityAsPdf(document.createElement("section"))

    expect(result).toEqual({ success: false, error: "Image load failed" })
    expect(mockLogError).toHaveBeenCalledWith(
      "[activityExport] PDF export failed:",
      "Image load failed"
    )
  })

  it("handles the image-load timeout and non-Error rejection values", async () => {
    vi.useFakeTimers()
    setImageBehavior("timeout")
    const timeoutPromise = exportActivityAsPdf(document.createElement("section"))
    await Promise.resolve()
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(10_000)
    await expect(timeoutPromise).resolves.toEqual({
      success: false,
      error: "Image load timed out",
    })

    mockToPng.mockRejectedValueOnce("not an Error")
    await expect(exportActivityAsPdf(document.createElement("section"))).resolves.toEqual({
      success: false,
      error: "PDF export failed",
    })
  })

  it("renders a double-density PNG and clicks an activity.png download", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    const createElement = vi.spyOn(document, "createElement")
    const element = document.createElement("section")

    await expect(exportActivityAsPng(element)).resolves.toEqual({ success: true })

    expect(mockToPng).toHaveBeenCalledWith(element, { pixelRatio: 2 })
    const anchor = createElement.mock.results.at(-1)?.value as HTMLAnchorElement
    expect(anchor.getAttribute("href")).toBe("data:image/png;base64,test")
    expect(anchor.download).toBe("activity.png")
    expect(click).toHaveBeenCalledTimes(1)
    expect(click.mock.contexts[0]).toBe(anchor)
  })

  it("lays out a wide capture on a landscape A4 page scaled to the page width", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 0, 5, 12, 0, 0))
    const expectedDate = new Date(2026, 0, 5, 12, 0, 0).toLocaleDateString()
    stubMicrotaskImage(380, 190)
    const element = document.createElement("section")

    await expect(exportActivityAsPdf(element)).resolves.toEqual({ success: true })

    expect(mockToPng).toHaveBeenCalledWith(element, { pixelRatio: 2 })
    expect(mockJsPDF).toHaveBeenCalledWith({ orientation: "landscape", unit: "mm", format: "a4" })
    expect(pdf.setFontSize.mock.calls).toEqual([[14], [8]])
    expect(pdf.text.mock.calls).toEqual([
      ["Activity", 10, 12],
      [expectedDate, 10, 17],
    ])
    // 190mm usable width / 380px = 0.5 is the binding scale.
    expect(pdf.addImage).toHaveBeenCalledWith("data:image/png;base64,test", "PNG", 10, 22, 190, 95)
    expect(pdf.save).toHaveBeenCalledWith("activity.pdf")
    // A settled load must cancel the 10s guard instead of leaving it pending.
    expect(vi.getTimerCount()).toBe(0)
  })

  it("scales a tall capture to the height left below the header", async () => {
    stubMicrotaskImage(131, 524)

    await exportActivityAsPdf(document.createElement("section"), "Tall", "tall.pdf")

    // 297mm - 25mm header - 10mm margin = 262mm usable height / 524px = 0.5.
    expect(pdf.addImage).toHaveBeenCalledWith(
      "data:image/png;base64,test",
      "PNG",
      10,
      22,
      65.5,
      262
    )
  })

  it("keeps a square capture in portrait orientation", async () => {
    stubMicrotaskImage(200, 200)

    await exportActivityAsPdf(document.createElement("section"), "Square", "square.pdf")

    expect(mockJsPDF).toHaveBeenCalledWith({ orientation: "portrait", unit: "mm", format: "a4" })
  })

  it("cancels the load guard when the image fails", async () => {
    vi.useFakeTimers()
    stubMicrotaskImage(380, 190, "error")

    await expect(exportActivityAsPdf(document.createElement("section"))).resolves.toEqual({
      success: false,
      error: "Image load failed",
    })
    expect(vi.getTimerCount()).toBe(0)
  })
})
