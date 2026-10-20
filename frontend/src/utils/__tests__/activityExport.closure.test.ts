import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { mockFetch, mockJsPDF, mockLogError, mockToPng } = vi.hoisted(() => ({
  mockFetch: vi.fn(),
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
  setFont: vi.fn(),
  text: vi.fn(),
  addFileToVFS: vi.fn(),
  addFont: vi.fn(),
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

const stubSynchronousImage = (width: number, height: number) => {
  class FakeImage {
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    readonly width = width
    readonly height = height

    set src(_value: string) {
      this.onload?.()
    }
  }
  vi.stubGlobal("Image", FakeImage)
}

const installManualTimeouts = () => {
  let nextId = 0
  const timers = new Map<number, { callback: () => void; delay: number }>()

  vi.spyOn(globalThis, "setTimeout").mockImplementation((callback, delay) => {
    const id = ++nextId
    if (typeof callback === "function") {
      timers.set(id, { callback: () => callback(), delay: Number(delay ?? 0) })
    }
    return id as unknown as ReturnType<typeof setTimeout>
  })
  vi.spyOn(globalThis, "clearTimeout").mockImplementation((handle) => {
    timers.delete(handle as unknown as number)
  })

  return {
    pending: () => Array.from(timers, ([id, timer]) => ({ id, delay: timer.delay })),
    fire: (id: number) => {
      const timer = timers.get(id)
      timers.delete(id)
      timer?.callback()
    },
  }
}

beforeEach(() => {
  mockToPng.mockReset()
  mockToPng.mockResolvedValue("data:image/png;base64,test")
  mockLogError.mockReset()
  mockJsPDF.mockReset()
  pdf.setFontSize.mockReset()
  pdf.setFont.mockReset()
  pdf.text.mockReset()
  pdf.addFileToVFS.mockReset()
  pdf.addFont.mockReset()
  pdf.addImage.mockReset()
  pdf.save.mockReset()
  mockFetch.mockReset().mockResolvedValue(new Response(new Uint8Array([0, 1, 2])))
  vi.stubGlobal("fetch", mockFetch)
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

  it("registers the embedded Latin and Cyrillic font for arbitrary supported titles and dates", async () => {
    stubMicrotaskImage(600, 800)
    const title = "École / Łódź / Việt Nam / Москва / ӿ"

    await expect(
      exportActivityAsPdf(document.createElement("section"), title, "unicode.pdf")
    ).resolves.toEqual({ success: true })

    expect(mockFetch).toHaveBeenCalledOnce()
    expect(pdf.addFileToVFS).toHaveBeenCalledWith("inter-latin-cyrillic-400.ttf", "AAEC")
    expect(pdf.addFont).toHaveBeenCalledWith(
      "inter-latin-cyrillic-400.ttf",
      "InterLatinCyrillic",
      "normal"
    )
    expect(pdf.setFont).toHaveBeenCalledWith("InterLatinCyrillic", "normal")
    expect(pdf.text).toHaveBeenCalledWith(title, 10, 12)
    expect(pdf.text).toHaveBeenCalledWith(new Date().toLocaleDateString(), 10, 17)
  })

  it("does not save a PDF if the embedded font asset cannot be loaded", async () => {
    stubMicrotaskImage(600, 800)
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 404 }))

    await expect(
      exportActivityAsPdf(document.createElement("section"), "Активность")
    ).resolves.toEqual({
      success: false,
      error: "Activity PDF font could not be loaded",
    })
    expect(pdf.save).not.toHaveBeenCalled()
  })

  it("bounds the font request and aborts when response headers never arrive", async () => {
    const timers = installManualTimeouts()
    stubSynchronousImage(600, 800)
    let requestSignal: AbortSignal | undefined
    let markFetchStarted!: () => void
    const fetchStarted = new Promise<void>((resolve) => {
      markFetchStarted = resolve
    })
    mockFetch.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      markFetchStarted()
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true }
        )
      })
    })

    let result: Awaited<ReturnType<typeof exportActivityAsPdf>> | undefined
    const exportPromise = exportActivityAsPdf(document.createElement("section"), "Активность").then(
      (value) => {
        result = value
        return value
      }
    )
    await fetchStarted
    expect(mockFetch).toHaveBeenCalledOnce()
    const pendingTimers = timers.pending()
    expect(pendingTimers.map(({ delay }) => delay)).toEqual([10_000])
    const [fontTimer] = pendingTimers
    if (!fontTimer) throw new Error("Font request timeout was not scheduled")
    timers.fire(fontTimer.id)

    await expect(exportPromise).resolves.toEqual({
      success: false,
      error: "Activity PDF font load timed out",
    })
    expect(result).toEqual({ success: false, error: "Activity PDF font load timed out" })
    expect(requestSignal?.aborted).toBe(true)
    expect(pdf.save).not.toHaveBeenCalled()
    expect(timers.pending()).toHaveLength(0)
  })

  it("uses the same bound for a font response whose body never finishes", async () => {
    const timers = installManualTimeouts()
    stubSynchronousImage(600, 800)
    let requestSignal: AbortSignal | undefined
    let markBodyStarted!: () => void
    const bodyStarted = new Promise<void>((resolve) => {
      markBodyStarted = resolve
    })
    const response = new Response(new Uint8Array([0, 1, 2]))
    vi.spyOn(response, "arrayBuffer").mockImplementation(() => {
      markBodyStarted()
      return new Promise<ArrayBuffer>(() => {})
    })
    mockFetch.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      return Promise.resolve(response)
    })

    let result: Awaited<ReturnType<typeof exportActivityAsPdf>> | undefined
    const exportPromise = exportActivityAsPdf(document.createElement("section"), "Активность").then(
      (value) => {
        result = value
        return value
      }
    )
    await bodyStarted
    expect(mockFetch).toHaveBeenCalledOnce()
    const pendingTimers = timers.pending()
    expect(pendingTimers.map(({ delay }) => delay)).toEqual([10_000])
    const [fontTimer] = pendingTimers
    if (!fontTimer) throw new Error("Font request timeout was not scheduled")
    timers.fire(fontTimer.id)

    await expect(exportPromise).resolves.toEqual({
      success: false,
      error: "Activity PDF font load timed out",
    })
    expect(result).toEqual({ success: false, error: "Activity PDF font load timed out" })
    expect(requestSignal?.aborted).toBe(true)
    expect(pdf.save).not.toHaveBeenCalled()
    expect(timers.pending()).toHaveLength(0)
  })

  it("clears the font deadline after a successful body read", async () => {
    const timers = installManualTimeouts()
    stubSynchronousImage(600, 800)
    let requestSignal: AbortSignal | undefined
    const response = new Response(new Uint8Array([0, 1, 2]))
    vi.spyOn(response, "arrayBuffer").mockImplementation(async () => {
      expect(timers.pending().map(({ delay }) => delay)).toEqual([10_000])
      return new Uint8Array([0, 1, 2]).buffer
    })
    mockFetch.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      return Promise.resolve(response)
    })

    await expect(
      exportActivityAsPdf(document.createElement("section"), "Активность")
    ).resolves.toEqual({ success: true })

    expect(requestSignal).toBeDefined()
    expect(requestSignal?.aborted).toBe(false)
    expect(pdf.save).toHaveBeenCalledOnce()
    expect(timers.pending()).toHaveLength(0)
  })

  it("clears the font deadline and does not save when body reading fails", async () => {
    const timers = installManualTimeouts()
    stubSynchronousImage(600, 800)
    const response = new Response(new Uint8Array([0, 1, 2]))
    vi.spyOn(response, "arrayBuffer").mockImplementation(async () => {
      expect(timers.pending().map(({ delay }) => delay)).toEqual([10_000])
      throw new Error("font body unavailable")
    })
    mockFetch.mockResolvedValueOnce(response)

    await expect(
      exportActivityAsPdf(document.createElement("section"), "Активность")
    ).resolves.toEqual({ success: false, error: "font body unavailable" })

    expect(pdf.save).not.toHaveBeenCalled()
    expect(timers.pending()).toHaveLength(0)
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
