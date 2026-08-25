import { describe, it, expect, vi, beforeEach } from "vitest"
import { exportActivityAsPng, exportActivityAsPdf } from "../activityExport"

// Mock dependencies
vi.mock("html-to-image", () => ({
  toPng: vi.fn().mockResolvedValue("data:image/png;base64,test"),
}))

vi.mock("jspdf", () => ({
  jsPDF: vi.fn(
    class MockJsPdf {
      internal = {
        pageSize: {
          getWidth: () => 210,
          getHeight: () => 297,
        },
      }
      setFontSize = vi.fn()
      text = vi.fn()
      addImage = vi.fn()
      save = vi.fn()
    }
  ),
}))

vi.mock("@/app/logger", () => ({
  logError: vi.fn(),
}))

describe("activityExport", () => {
  describe("exportActivityAsPng", () => {
    let mockElement: HTMLElement

    beforeEach(() => {
      mockElement = document.createElement("div")
      vi.spyOn(document, "createElement")
      const mockAnchor = { click: vi.fn(), href: "", download: "" } as unknown as HTMLAnchorElement
      vi.mocked(document.createElement).mockReturnValueOnce(
        mockAnchor as unknown as HTMLAnchorElement
      )
    })

    it("successfully triggers a PNG download", async () => {
      const result = await exportActivityAsPng(mockElement)
      expect(result.success).toBe(true)
      expect(document.createElement).toHaveBeenCalledWith("a")
    })
  })

  describe("exportActivityAsPdf", () => {
    let mockElement: HTMLElement

    beforeEach(() => {
      mockElement = document.createElement("div")
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
      const result = await exportActivityAsPdf(mockElement, "Activity Log", "activity.pdf")
      expect(result.success).toBe(true)
    })
  })
})
