import type { jsPDF } from "jspdf"

const PDF_FONT_LOAD_TIMEOUT_MS = 10_000
const PDF_FONT_FILE = "inter-latin-cyrillic-400.ttf"
const PDF_FONT_FAMILY = "InterLatinCyrillic"
const BASE64_CHUNK_SIZE = 0x4000

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ""

  for (let offset = 0; offset < bytes.length; offset += BASE64_CHUNK_SIZE) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + BASE64_CHUNK_SIZE))
  }

  return btoa(binary)
}

async function loadPdfFont(fontUrl: string, label: string): Promise<ArrayBuffer> {
  const controller = new AbortController()
  let rejectTimeout!: (reason: Error) => void
  const timeout = new Promise<never>((_resolve, reject) => {
    rejectTimeout = reject
  })
  const timeoutId = setTimeout(() => {
    rejectTimeout(new Error(`${label} PDF font load timed out`))
    controller.abort()
  }, PDF_FONT_LOAD_TIMEOUT_MS)
  const request = async () => {
    const response = await fetch(fontUrl, { signal: controller.signal })
    if (controller.signal.aborted) throw new Error(`${label} PDF font load timed out`)
    if (!response.ok) throw new Error(`${label} PDF font could not be loaded`)
    return response.arrayBuffer()
  }

  try {
    return await Promise.race([request(), timeout])
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function registerPdfFont(pdf: jsPDF, label = "Activity"): Promise<void> {
  const { default: fontUrl } = await import("@/assets/fonts/inter-latin-cyrillic-400.ttf?url")
  const fontBase64 = arrayBufferToBase64(await loadPdfFont(fontUrl, label))
  pdf.addFileToVFS(PDF_FONT_FILE, fontBase64)
  pdf.addFont(PDF_FONT_FILE, PDF_FONT_FAMILY, "normal")
  pdf.setFont(PDF_FONT_FAMILY, "normal")
}
