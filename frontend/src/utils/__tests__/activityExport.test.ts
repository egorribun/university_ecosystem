import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import fontUrl from "@/assets/fonts/inter-latin-cyrillic-400.ttf?url"
import { exportActivityAsPng, exportActivityAsPdf } from "../activityExport"

const { pdfMocks } = vi.hoisted(() => ({
  pdfMocks: {
    addFileToVFS: vi.fn(),
    addFont: vi.fn(),
    setFont: vi.fn(),
    save: vi.fn(),
  },
}))

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
      addFileToVFS = pdfMocks.addFileToVFS
      addFont = pdfMocks.addFont
      setFont = pdfMocks.setFont
      setFontSize = vi.fn()
      text = vi.fn()
      addImage = vi.fn()
      save = pdfMocks.save
    }
  ),
}))

vi.mock("@/app/logger", () => ({
  logError: vi.fn(),
}))

describe("activityExport", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  describe("exportActivityAsPng", () => {
    let mockElement: HTMLElement

    beforeEach(() => {
      mockElement = document.createElement("div")
      vi.spyOn(document, "createElement")
      const mockAnchor = { click: vi.fn(), href: "", download: "" } as unknown as HTMLAnchorElement
      vi.mocked(document.createElement).mockReturnValueOnce(mockAnchor)
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
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Uint8Array([0, 1, 2]))))
      vi.stubGlobal(
        "Image",
        class {
          onload: (() => void) | null = null
          onerror: (() => void) | null = null
          readonly width = 800
          readonly height = 600

          set src(_value: string) {
            queueMicrotask(() => this.onload?.())
          }
        }
      )
    })

    it("successfully triggers a PDF save", async () => {
      const result = await exportActivityAsPdf(mockElement, "Activity Log", "activity.pdf")

      expect(result).toEqual({ success: true })
      expect(fetch).toHaveBeenCalledExactlyOnceWith(fontUrl, {
        signal: expect.any(AbortSignal),
      })
      expect(pdfMocks.addFileToVFS).toHaveBeenCalledWith("inter-latin-cyrillic-400.ttf", "AAEC")
      expect(pdfMocks.addFont).toHaveBeenCalledWith(
        "inter-latin-cyrillic-400.ttf",
        "InterLatinCyrillic",
        "normal"
      )
      expect(pdfMocks.setFont).toHaveBeenCalledWith("InterLatinCyrillic", "normal")
      expect(pdfMocks.save).toHaveBeenCalledExactlyOnceWith("activity.pdf")
    })
  })
})
