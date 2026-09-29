import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import {
  generateGoogleCalendarUrl,
  exportScheduleAsPng,
  exportScheduleAsPdf,
} from "../scheduleExport"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import { toPng } from "html-to-image"
import { jsPDF } from "jspdf"
import { logError } from "@/app/logger"
import { withExpectedConsole } from "@/tests/strictConsole"

const { pdf } = vi.hoisted(() => ({
  pdf: {
    internal: {
      pageSize: {
        getWidth: () => 210,
        getHeight: () => 297,
      },
    },
    setFontSize: vi.fn(),
    text: vi.fn(),
    addImage: vi.fn(),
    save: vi.fn(),
  },
}))

// Mock dependencies
vi.mock("html-to-image", () => ({
  toPng: vi.fn().mockResolvedValue("data:image/png;base64,test"),
}))

vi.mock("jspdf", () => ({
  jsPDF: vi.fn(function MockJsPdf(this: typeof pdf) {
    Object.assign(this, pdf)
  }),
}))

vi.mock("@/app/logger", () => ({
  logError: vi.fn((...args) => {
    console.error("LOGGED ERROR:", ...args)
  }),
}))

const DATA_URL = "data:image/png;base64,test"

/** Image whose load settles in a microtask, so no timer other than the guard runs. */
const stubImage = (width: number, height: number, outcome: "load" | "error" = "load") => {
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

describe("scheduleExport", () => {
  describe("generateGoogleCalendarUrl", () => {
    const mockLesson: Lesson = {
      id: "1",
      subject: "Math",
      teacher: "Newton",
      room: "A101",
      start_time: "10:00",
      end_time: "11:30",
      lesson_type: "Lecture",
      weekday: "mon",
      parity: "both",
    }
    const mockDate = new Date(2026, 3, 25) // April 25, 2026

    it("generates a valid Google Calendar URL", () => {
      const url = generateGoogleCalendarUrl(mockLesson, mockDate)
      expect(url).toContain("https://calendar.google.com/calendar/r/eventedit")
      expect(url).toContain("text=Math+%28Newton%29")
      expect(url).toContain("dates=20260425T100000%2F20260425T113000")
      expect(url).toContain("location=A101")
      expect(url).toContain("details=Lecture")
    })

    it("uses labels for fallback values", () => {
      const lessonWithoutSubject: Lesson = { ...mockLesson, subject: undefined }
      const url = generateGoogleCalendarUrl(lessonWithoutSubject, mockDate, {
        lessonFallback: "Untitled Lesson",
      })
      expect(url).toContain("text=Untitled+Lesson+%28Newton%29")
    })

    it("handles missing subject, teacher, times, and lesson_type", () => {
      const emptyLesson = {
        id: "2",
        weekday: "tue",
        parity: "even",
      } as unknown as Lesson
      const url = generateGoogleCalendarUrl(emptyLesson, mockDate)
      expect(url).toContain("text=Lesson")
      expect(url).toContain("dates=20260425T090000%2F20260425T103000")
      expect(url).toContain("location=")
      expect(url).toContain("details=")
    })

    it("handles custom typePrefix label replacement", () => {
      const url = generateGoogleCalendarUrl(mockLesson, mockDate, {
        typePrefix: "Type: {{type}}",
      })
      expect(url).toContain("details=Type%3A+Lecture")
    })

    it("uses an empty type inside a custom typePrefix when lesson_type is absent", () => {
      const url = generateGoogleCalendarUrl({ ...mockLesson, lesson_type: undefined }, mockDate, {
        typePrefix: "Type: {{type}}",
      })
      expect(url).toContain("details=Type%3A+")
    })

    it("builds the exact URL with zero-padded single-digit day, hours and minutes", () => {
      const lesson = {
        id: "3",
        subject: "Math",
        start_time: "08:05",
        end_time: "09:05",
        weekday: "mon",
        parity: "both",
      } as unknown as Lesson
      expect(generateGoogleCalendarUrl(lesson, new Date(2026, 0, 5))).toBe(
        "https://calendar.google.com/calendar/r/eventedit?action=TEMPLATE&text=Math" +
          "&dates=20260105T080500%2F20260105T090500&location=&details="
      )
    })

    it("leaves the type placeholder empty in the exact URL when lesson_type is absent", () => {
      const url = generateGoogleCalendarUrl({ ...mockLesson, lesson_type: undefined }, mockDate, {
        typePrefix: "Type: {{type}}",
      })
      expect(url).toBe(
        "https://calendar.google.com/calendar/r/eventedit?action=TEMPLATE&text=Math+%28Newton%29" +
          "&dates=20260425T100000%2F20260425T113000&location=A101&details=Type%3A+"
      )
    })
  })

  describe("exportScheduleAsPng", () => {
    let mockElement: HTMLElement

    let createElementSpy: any
    let mockAnchor: HTMLAnchorElement

    beforeEach(() => {
      mockElement = document.createElement("div")
      createElementSpy = vi.spyOn(document, "createElement")
      // Mock click on anchor
      mockAnchor = { click: vi.fn(), href: "", download: "" } as unknown as HTMLAnchorElement
      vi.mocked(document.createElement).mockReturnValue(mockAnchor as unknown as HTMLAnchorElement)
    })

    afterEach(() => {
      createElementSpy.mockRestore()
    })

    it("successfully triggers a PNG download", async () => {
      const result = await exportScheduleAsPng(mockElement)
      expect(result.success).toBe(true)
      expect(document.createElement).toHaveBeenCalledWith("a")
    })

    it("renders at double pixel ratio without fonts and clicks a schedule.png download", async () => {
      await exportScheduleAsPng(mockElement)
      expect(toPng).toHaveBeenCalledWith(mockElement, { pixelRatio: 2, skipFonts: true })
      expect(mockAnchor.href).toBe(DATA_URL)
      expect(mockAnchor.download).toBe("schedule.png")
      expect(mockAnchor.click).toHaveBeenCalledTimes(1)
    })

    it("handles error during toPng import or generation", async () => {
      vi.mocked(toPng).mockRejectedValueOnce(new Error("toPng error"))
      const result = await withExpectedConsole("error", "LOGGED ERROR:", () =>
        exportScheduleAsPng(mockElement)
      )
      expect(result.success).toBe(false)
      expect(result.error).toBe("toPng error")
      expect(logError).toHaveBeenCalledWith("[scheduleExport] PNG export failed:", "toPng error")
    })

    it("handles non-Error rejection", async () => {
      vi.mocked(toPng).mockRejectedValueOnce("some string error")
      const result = await withExpectedConsole("error", "LOGGED ERROR:", () =>
        exportScheduleAsPng(mockElement)
      )
      expect(result.success).toBe(false)
      expect(result.error).toBe("PNG export failed")
    })
  })

  describe("exportScheduleAsPdf", () => {
    let mockElement: HTMLElement
    let originalImage: typeof Image

    beforeEach(() => {
      mockElement = document.createElement("div")
      originalImage = global.Image
    })

    afterEach(() => {
      global.Image = originalImage
    })

    it("successfully triggers a PDF save (landscape)", async () => {
      global.Image = class {
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        _src: string = ""
        width: number = 800
        height: number = 600
        set src(v: string) {
          this._src = v
          setTimeout(() => this.onload?.(), 10)
        }
        get src() {
          return this._src
        }
      } as unknown as typeof Image

      const result = await exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")
      expect(result.success).toBe(true)
    })

    it("successfully triggers a PDF save (portrait)", async () => {
      global.Image = class {
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        _src: string = ""
        width: number = 400
        height: number = 600
        set src(v: string) {
          this._src = v
          setTimeout(() => this.onload?.(), 10)
        }
        get src() {
          return this._src
        }
      } as unknown as typeof Image

      const result = await exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")
      expect(result.success).toBe(true)
    })

    it("handles image load failure", async () => {
      global.Image = class {
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        _src: string = ""
        width: number = 0
        height: number = 0
        set src(v: string) {
          this._src = v
          setTimeout(() => this.onerror?.(), 10)
        }
        get src() {
          return this._src
        }
      } as unknown as typeof Image

      const result = await withExpectedConsole("error", "LOGGED ERROR:", () =>
        exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")
      )
      expect(result.success).toBe(false)
      expect(result.error).toBe("Image load failed")
    })

    it("handles image load timeout", async () => {
      vi.useFakeTimers()
      global.Image = class {
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        src: string = ""
        width: number = 800
        height: number = 600
      } as unknown as typeof Image

      const result = await withExpectedConsole("error", "LOGGED ERROR:", async () => {
        const promise = exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")

        // Fast-forward time to trigger timeout while the expected diagnostic
        // is active, so the rejection-path logger remains scoped to this test.
        await vi.advanceTimersByTimeAsync(11000)

        return promise
      })
      expect(result.success).toBe(false)
      expect(result.error).toBe("Image load timed out")
      vi.useRealTimers()
    })

    it("handles error during toPng or PDF generation", async () => {
      vi.mocked(toPng).mockRejectedValueOnce(new Error("PDF generation error"))
      const result = await withExpectedConsole("error", "LOGGED ERROR:", () =>
        exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")
      )
      expect(result.success).toBe(false)
      expect(result.error).toBe("PDF generation error")
      expect(logError).toHaveBeenCalledWith(
        "[scheduleExport] PDF export failed:",
        "PDF generation error"
      )
    })

    it("uses the generic PDF error for a non-Error rejection", async () => {
      vi.mocked(toPng).mockRejectedValueOnce("PDF generation failed")
      const result = await withExpectedConsole("error", "LOGGED ERROR:", () =>
        exportScheduleAsPdf(mockElement)
      )
      expect(result).toEqual({ success: false, error: "PDF export failed" })
    })
  })

  describe("exportScheduleAsPdf layout", () => {
    afterEach(() => {
      vi.useRealTimers()
      vi.unstubAllGlobals()
    })

    it("lays out a wide grid on a landscape A4 page scaled to the page width", async () => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2026, 0, 5, 12, 0, 0))
      const expectedDate = new Date(2026, 0, 5, 12, 0, 0).toLocaleDateString()
      stubImage(380, 190)
      const element = document.createElement("div")

      await expect(exportScheduleAsPdf(element, "Week 2", "week.pdf")).resolves.toEqual({
        success: true,
      })

      expect(toPng).toHaveBeenCalledWith(element, { pixelRatio: 2, skipFonts: true })
      expect(jsPDF).toHaveBeenCalledWith({ orientation: "landscape", unit: "mm", format: "a4" })
      expect(pdf.setFontSize.mock.calls).toEqual([[14], [8]])
      expect(pdf.text.mock.calls).toEqual([
        ["Week 2", 10, 12],
        [expectedDate, 10, 17],
      ])
      // 190mm usable width / 380px = 0.5 is the binding scale.
      expect(pdf.addImage).toHaveBeenCalledWith(DATA_URL, "PNG", 10, 22, 190, 95)
      expect(pdf.save).toHaveBeenCalledWith("week.pdf")
      // A settled load must cancel the 10s guard instead of leaving it pending.
      expect(vi.getTimerCount()).toBe(0)
    })

    it("lays out a tall grid in portrait scaled to the height below the header", async () => {
      stubImage(131, 524)

      await expect(exportScheduleAsPdf(document.createElement("div"))).resolves.toEqual({
        success: true,
      })

      expect(jsPDF).toHaveBeenCalledWith({ orientation: "portrait", unit: "mm", format: "a4" })
      expect(pdf.text).toHaveBeenNthCalledWith(1, "Schedule", 10, 12)
      // 297mm - 25mm header - 10mm margin = 262mm usable height / 524px = 0.5.
      expect(pdf.addImage).toHaveBeenCalledWith(DATA_URL, "PNG", 10, 22, 65.5, 262)
      expect(pdf.save).toHaveBeenCalledWith("schedule.pdf")
    })

    it("keeps a square grid in portrait orientation", async () => {
      stubImage(200, 200)

      await exportScheduleAsPdf(document.createElement("div"), "Square", "square.pdf")

      expect(jsPDF).toHaveBeenCalledWith({ orientation: "portrait", unit: "mm", format: "a4" })
    })

    it("cancels the load guard when the image fails", async () => {
      vi.useFakeTimers()
      stubImage(380, 190, "error")

      const result = await withExpectedConsole("error", "LOGGED ERROR:", () =>
        exportScheduleAsPdf(document.createElement("div"), "Week 2", "week.pdf")
      )

      expect(result).toEqual({ success: false, error: "Image load failed" })
      expect(vi.getTimerCount()).toBe(0)
      expect(pdf.save).not.toHaveBeenCalled()
    })
  })
})
