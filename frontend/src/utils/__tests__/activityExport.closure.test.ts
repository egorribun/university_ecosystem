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

beforeEach(() => {
  mockToPng.mockReset()
  mockToPng.mockResolvedValue("data:image/png;base64,test")
  mockLogError.mockReset()
  mockJsPDF.mockReset()
  mockJsPDF.mockReturnValue(pdf)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
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
})
