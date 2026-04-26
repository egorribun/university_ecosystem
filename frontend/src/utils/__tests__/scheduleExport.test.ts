import { describe, it, expect, vi, beforeEach, type Mock } from "vitest"
import { generateGoogleCalendarUrl, exportScheduleAsPng, exportScheduleAsPdf } from "../scheduleExport"
import type { Lesson } from "@/components/schedule/scheduleUtils"

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
  logError: vi.fn(),
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
  })

  describe("exportScheduleAsPng", () => {
    let mockElement: HTMLElement

    beforeEach(() => {
      mockElement = document.createElement("div")
      vi.spyOn(document, "createElement")
      // Mock click on anchor
      const mockAnchor = { click: vi.fn(), href: "", download: "" } as unknown as HTMLAnchorElement
      ;(document.createElement as unknown as Mock).mockReturnValueOnce(mockAnchor)
    })

    it("successfully triggers a PNG download", async () => {
      const result = await exportScheduleAsPng(mockElement)
      expect(result.success).toBe(true)
      expect(document.createElement).toHaveBeenCalledWith("a")
    })
  })

  describe("exportScheduleAsPdf", () => {
    let mockElement: HTMLElement

    beforeEach(() => {
      mockElement = document.createElement("div")
      // Mock Image and its events
      global.Image = class {
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        src: string = ""
        width: number = 800
        height: number = 600
        constructor() {
          setTimeout(() => this.onload?.(), 10)
        }
      } as unknown as typeof Image
    })

    it("successfully triggers a PDF save", async () => {
      const result = await exportScheduleAsPdf(mockElement, "Test Schedule", "test.pdf")
      expect(result.success).toBe(true)
    })
  })
})
