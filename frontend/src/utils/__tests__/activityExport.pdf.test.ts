import { mkdir, readFile, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { afterEach, describe, expect, it, vi } from "vitest"
import fontUrl from "@/assets/fonts/inter-latin-cyrillic-400.ttf?url"

const { capturedPdfs } = vi.hoisted(() => ({ capturedPdfs: [] as Uint8Array[] }))
const pngDataUrl =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="

vi.mock("html-to-image", () => ({ toPng: vi.fn().mockResolvedValue(pngDataUrl) }))
vi.mock("jspdf", async (importOriginal) => {
  const actual = await importOriginal<typeof import("jspdf")>()
  const capturingJsPDF = new Proxy(actual.jsPDF, {
    construct(target, args) {
      const pdf = Reflect.construct(target, args) as import("jspdf").jsPDF
      Object.defineProperty(pdf, "save", {
        configurable: true,
        value: (): import("jspdf").jsPDF => {
          const output = pdf.output("arraybuffer")
          if (!(output instanceof ArrayBuffer)) throw new Error("jsPDF did not return PDF bytes")
          capturedPdfs.push(new Uint8Array(output))
          return pdf
        },
      })
      return pdf
    },
  })

  return { ...actual, jsPDF: capturingJsPDF }
})

import { exportActivityAsPdf } from "../activityExport"

describe("activity PDF font embedding", () => {
  afterEach(() => {
    capturedPdfs.length = 0
    vi.unstubAllGlobals()
  })

  it("generates real jsPDF files with searchable English, Cyrillic, and extended Latin text", async () => {
    const fontBytes = await readFile("src/assets/fonts/inter-latin-cyrillic-400.ttf")
    const titles = ["Activity", "Активность", "École / Łódź / Việt Nam / Москва / ӿ"]
    const fetchSpy = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe(fontUrl)
      return new Response(fontBytes)
    })
    vi.stubGlobal("fetch", fetchSpy)

    class LoadedImage {
      readonly width = 1
      readonly height = 1
      onload: (() => void) | null = null
      onerror: (() => void) | null = null

      set src(_value: string) {
        queueMicrotask(() => this.onload?.())
      }
    }
    vi.stubGlobal("Image", LoadedImage)

    expect(fontUrl).not.toMatch(/^data:/)
    expect(fontBytes.byteLength).toBeGreaterThan(4_096)

    for (const [index, title] of titles.entries()) {
      await expect(
        exportActivityAsPdf(document.createElement("section"), title, `activity-${index}.pdf`)
      ).resolves.toEqual({ success: true })
    }

    expect(fetchSpy).toHaveBeenCalledTimes(titles.length)
    expect(capturedPdfs).toHaveLength(titles.length)
    for (const bytes of capturedPdfs) {
      const pdfText = new TextDecoder("latin1").decode(bytes)
      expect(pdfText.startsWith("%PDF-")).toBe(true)
      expect(pdfText).toContain("/FontFile2")
      expect(pdfText).toContain("/ToUnicode")
      expect(bytes.byteLength).toBeGreaterThan(10_000)
    }

    const proofDirectory = process.env["AUD015_PDF_PROOF_DIR"]
    if (proofDirectory) {
      await mkdir(proofDirectory, { recursive: true })
      await Promise.all(
        capturedPdfs.map((bytes, index) =>
          writeFile(join(proofDirectory, `activity-${index}.pdf`), bytes)
        )
      )
    }
  })
})
