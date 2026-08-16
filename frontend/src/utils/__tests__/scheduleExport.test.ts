import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import {
  generateGoogleCalendarUrl,
  exportScheduleAsPng,
  exportScheduleAsPdf,
} from "../scheduleExport"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import { toPng } from "html-to-image"

// Mock dependencies
vi.mock("html-to-image", () => ({
  toPng: vi.fn().mockResolvedValue("data:image/png;base64,test"),
}))

vi.mock("jspdf", () => ({
  jsPDF: vi.fn().mockImplementation(() => ({
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
  })),
}))

vi.mock("@/app/logger", () => ({
  logError: vi.fn((...args) => {
    console.error("LOGGED ERROR:", ...args)
  }),
}))

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
      const url = generateGoogleCalendarUrl(
        { ...mockLesson, lesson_type: undefined },
        mockDate,
        { typePrefix: "Type: {{type}}" }
      )
      expect(url).toContain("details=Type%3A+")
    })
  })

  describe("exportScheduleAsPng", () => {
    let mockElement: HTMLElement

    let createElementSpy: any

    beforeEach(() => {
      mockElement = document.createElement("div")
      createElementSpy = vi.spyOn(document, "createElement")
      // Mock click on anchor
      const mockAnchor = { click: vi.fn(), href: "", download: "" } as unknown as HTMLAnchorElement
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

    it("handles error during toPng import or generation", async () => {
      vi.mocked(toPng).mockRejectedValueOnce(new Error("toPng error"))
      const result = await exportScheduleAsPng(mockElement)
      expect(result.success).toBe(false)
      expect(result.error).toBe("toPng error")
    })

    it("handles non-Error rejection", async () => {
      vi.mocked(toPng).mockRejectedValueOnce("some string error")
      const result = await exportScheduleAsPng(mockElement)
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

      const result = await exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")
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

      const promise = exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")

      // Fast-forward time to trigger timeout
      await vi.advanceTimersByTimeAsync(11000)

      const result = await promise
      expect(result.success).toBe(false)
      expect(result.error).toBe("Image load timed out")
      vi.useRealTimers()
    })

    it("handles error during toPng or PDF generation", async () => {
      vi.mocked(toPng).mockRejectedValueOnce(new Error("PDF generation error"))
      const result = await exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")
      expect(result.success).toBe(false)
      expect(result.error).toBe("PDF generation error")
    })

    it("uses the generic PDF error for a non-Error rejection", async () => {
      vi.mocked(toPng).mockRejectedValueOnce("PDF generation failed")
      const result = await exportScheduleAsPdf(mockElement)
      expect(result).toEqual({ success: false, error: "PDF export failed" })
    })
  })
})
