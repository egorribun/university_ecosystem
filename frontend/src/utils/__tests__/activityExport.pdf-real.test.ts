import { readFile } from "node:fs/promises"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import fontUrl from "@/assets/fonts/inter-latin-cyrillic-400.ttf?url"

const { documents, useBuiltinFont } = vi.hoisted(() => ({
  documents: [] as { save: ReturnType<typeof vi.fn>; bytes: Uint8Array | undefined }[],
  useBuiltinFont: { current: false },
}))

const pngDataUrl =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="

vi.mock("html-to-image", () => ({ toPng: vi.fn().mockResolvedValue(pngDataUrl) }))
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))
vi.mock("jspdf", async (importOriginal) => {
  const actual = await importOriginal<typeof import("jspdf")>()
  const capturingJsPDF = new Proxy(actual.jsPDF, {
    construct(target, args) {
      const pdf = Reflect.construct(target, args) as import("jspdf").jsPDF
      const entry: (typeof documents)[number] = { save: vi.fn(), bytes: undefined }
      entry.save.mockImplementation(() => {
        entry.bytes = new Uint8Array(pdf.output("arraybuffer"))
        return pdf
      })
      Object.defineProperty(pdf, "save", { configurable: true, value: entry.save })
      if (useBuiltinFont.current) {
        const setFont = pdf.setFont.bind(pdf)
        vi.spyOn(pdf, "setFont").mockImplementation((_family, style, weight) =>
          setFont("helvetica", style, weight)
        )
      }
      documents.push(entry)
      return pdf
    },
  })
  return { ...actual, jsPDF: capturingJsPDF }
})

import { exportActivityAsPdf } from "../activityExport"

/** Decode the active page font's PDF ToUnicode map, rather than trusting font markers alone. */
function extractPageText(bytes: Uint8Array): string[] {
  const pdf = new TextDecoder("latin1").decode(bytes)
  const getObject = (id: string): string => {
    const marker = `\n${id} 0 obj\n`
    const start = pdf.indexOf(marker)
    const end = pdf.indexOf("\nendobj", start + marker.length)
    if (start === -1 || end === -1) throw new Error(`Missing PDF object ${id}`)
    return pdf.slice(start + marker.length, end)
  }
  const page = /\/Type \/Page\b([\s\S]*?)\nendobj/.exec(pdf)?.[1]
  const resourcesId = page?.match(/\/Resources (\d+) 0 R/)?.[1]
  const contentsId = page?.match(/\/Contents (\d+) 0 R/)?.[1]
  if (!resourcesId || !contentsId) throw new Error("Missing page resources or contents")
  const resources = getObject(resourcesId)
  const contents = getObject(contentsId)
  const fonts = new Map(
    [...resources.matchAll(/\/(F\d+)\s+(\d+)\s+0\s+R/g)].map(([, name, id]) => [name, id])
  )
  const blocks = [...contents.matchAll(/\bBT\b([\s\S]*?)\bET\b/g)]
  if (blocks.length === 0) throw new Error("Page has no text")

  return blocks.map(([, block]) => {
    if (!block) throw new Error("Missing text block")
    const fontName = block.match(/\/(F\d+)\s+[\d.]+\s+Tf/)?.[1]
    const fontId = fontName && fonts.get(fontName)
    if (!fontId) throw new Error("Text block has no active font")
    const font = getObject(fontId)
    const unicodeId = font.match(/\/ToUnicode (\d+) 0 R/)?.[1]
    if (!unicodeId) throw new Error("Active text font has no Unicode map")
    const unicode = getObject(unicodeId)
    const charSection = /\d+ beginbfchar([\s\S]*?)endbfchar/.exec(unicode)?.[1]
    if (!charSection) throw new Error("Unicode map has no character mappings")
    const mappings = [...charSection.matchAll(/<([0-9a-f]{4})>\s*<([0-9a-f]{4})>/gi)]
    const glyphs = new Map(
      mappings.map(([, glyph, character]) => [glyph?.toLowerCase(), character])
    )
    const encoded = block.match(/<([0-9a-f]+)>\s*Tj/i)?.[1]
    if (!encoded || encoded.length % 4 !== 0) throw new Error("Missing CID text")
    return (encoded.match(/.{4}/g) ?? [])
      .map((glyph) => {
        const character = glyphs.get(glyph.toLowerCase())
        if (!character) throw new Error(`Missing Unicode mapping for ${glyph}`)
        return String.fromCharCode(Number.parseInt(character, 16))
      })
      .join("")
  })
}

describe("AUD-015 real Activity PDF", () => {
  beforeEach(() => {
    documents.length = 0
    useBuiltinFont.current = false
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-28T12:00:00Z"))
    vi.stubGlobal(
      "Image",
      class {
        readonly width = 1
        readonly height = 1
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        set src(_value: string) {
          queueMicrotask(() => this.onload?.())
        }
      }
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("maps Cyrillic and mixed-script titles and the date to Unicode in the generated PDF", async () => {
    const fontBytes = await readFile("src/assets/fonts/inter-latin-cyrillic-400.ttf")
    const fetchFont = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe(fontUrl)
      return new Response(fontBytes)
    })
    vi.stubGlobal("fetch", fetchFont)
    const titles = ["Активность", "École / Łódź / Việt Nam / Москва / ӿ"]
    const date = new Date().toLocaleDateString()

    for (const title of titles) {
      await expect(exportActivityAsPdf(document.createElement("section"), title)).resolves.toEqual({
        success: true,
      })
    }

    expect(fetchFont).toHaveBeenCalledTimes(titles.length)
    expect(documents).toHaveLength(titles.length)
    for (const [index, document] of documents.entries()) {
      expect(document.save).toHaveBeenCalledExactlyOnceWith("activity.pdf")
      expect(document.bytes).toBeDefined()
      if (!document.bytes) throw new Error("PDF was not saved")
      expect(extractPageText(document.bytes)).toEqual([titles[index], date])
    }
  })

  it("detects the original failure when the active font is forced to built-in Helvetica", async () => {
    const fontBytes = await readFile("src/assets/fonts/inter-latin-cyrillic-400.ttf")
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(fontBytes)))
    useBuiltinFont.current = true

    await expect(
      exportActivityAsPdf(document.createElement("section"), "Активность")
    ).resolves.toEqual({
      success: true,
    })
    const bytes = documents[0]?.bytes
    if (!bytes) throw new Error("Negative-control PDF was not saved")
    expect(() => extractPageText(bytes)).toThrow("Active text font has no Unicode map")
  })

  it.each([
    {
      scenario: "HTTP 404",
      load: () => Promise.resolve(new Response(null, { status: 404 })),
      error: "Activity PDF font could not be loaded",
    },
    {
      scenario: "a rejected request",
      load: () => Promise.reject(new Error("font request unavailable")),
      error: "font request unavailable",
    },
    {
      scenario: "a rejected response body",
      load: () => {
        const response = new Response(new Uint8Array([0]))
        vi.spyOn(response, "arrayBuffer").mockRejectedValue(new Error("font body unavailable"))
        return Promise.resolve(response)
      },
      error: "font body unavailable",
    },
  ])("does not save when font loading fails with $scenario", async ({ load, error }) => {
    vi.stubGlobal("fetch", vi.fn(load))

    await expect(
      exportActivityAsPdf(document.createElement("section"), "Активность")
    ).resolves.toEqual({ success: false, error })
    expect(documents).toHaveLength(1)
    expect(documents[0]?.save).not.toHaveBeenCalled()
    expect(documents[0]?.bytes).toBeUndefined()
  })
})
