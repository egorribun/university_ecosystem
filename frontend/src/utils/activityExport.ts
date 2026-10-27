/**
 * activityExport.ts — Multi-format export utilities for Activity page.
 * Follows scheduleExport.ts pattern (Wave 66). Dynamic imports only.
 */
import { logError } from "@/app/logger"
import i18n from "@/i18n/config"
import type { jsPDF } from "jspdf"

export interface ExportResult {
  success: boolean
  error?: string
}

const IMAGE_LOAD_TIMEOUT_MS = 10_000
const ACTIVITY_PDF_FONT_FILE = "inter-latin-cyrillic-400.ttf"
const ACTIVITY_PDF_FONT_FAMILY = "InterLatinCyrillic"
const BASE64_CHUNK_SIZE = 0x4000

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ""

  for (let offset = 0; offset < bytes.length; offset += BASE64_CHUNK_SIZE) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + BASE64_CHUNK_SIZE))
  }

  return btoa(binary)
}

async function loadActivityPdfFont(fontUrl: string): Promise<ArrayBuffer> {
  const controller = new AbortController()
  let rejectTimeout!: (reason: Error) => void
  const timeout = new Promise<never>((_resolve, reject) => {
    rejectTimeout = reject
  })
  const timeoutId = setTimeout(() => {
    rejectTimeout(new Error("Activity PDF font load timed out"))
    controller.abort()
  }, IMAGE_LOAD_TIMEOUT_MS)
  const request = async () => {
    const response = await fetch(fontUrl, { signal: controller.signal })
    if (controller.signal.aborted) throw new Error("Activity PDF font load timed out")
    if (!response.ok) throw new Error("Activity PDF font could not be loaded")
    return response.arrayBuffer()
  }

  try {
    return await Promise.race([request(), timeout])
  } finally {
    clearTimeout(timeoutId)
  }
}

async function registerActivityPdfFont(pdf: jsPDF): Promise<void> {
  const { default: fontUrl } = await import("@/assets/fonts/inter-latin-cyrillic-400.ttf?url")
  const fontBase64 = arrayBufferToBase64(await loadActivityPdfFont(fontUrl))
  pdf.addFileToVFS(ACTIVITY_PDF_FONT_FILE, fontBase64)
  pdf.addFont(ACTIVITY_PDF_FONT_FILE, ACTIVITY_PDF_FONT_FAMILY, "normal")
  pdf.setFont(ACTIVITY_PDF_FONT_FAMILY, "normal")
}

function loadImageWithTimeout(
  src: string,
  timeoutMs = IMAGE_LOAD_TIMEOUT_MS
): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const timer = setTimeout(() => {
      img.onload = null
      img.onerror = null
      reject(new Error("Image load timed out"))
    }, timeoutMs)
    img.onload = () => {
      clearTimeout(timer)
      resolve(img)
    }
    img.onerror = () => {
      clearTimeout(timer)
      reject(new Error("Image load failed"))
    }
    img.src = src
  })
}

export async function exportActivityAsPng(
  element: HTMLElement,
  filename = "activity.png"
): Promise<ExportResult> {
  try {
    const { toPng } = await import("html-to-image")
    const dataUrl = await toPng(element, { pixelRatio: 2 })
    const a = document.createElement("a")
    a.href = dataUrl
    a.download = filename
    a.click()
    return { success: true }
  } catch (err) {
    const message = err instanceof Error ? err.message : "PNG export failed"
    logError("[activityExport] PNG export failed:", message)
    return { success: false, error: message }
  }
}

export async function exportActivityAsPdf(
  element: HTMLElement,
  title = i18n.t("activity:title"),
  filename = "activity.pdf"
): Promise<ExportResult> {
  try {
    const [{ toPng }, { jsPDF }] = await Promise.all([import("html-to-image"), import("jspdf")])

    const dataUrl = await toPng(element, { pixelRatio: 2 })
    const img = await loadImageWithTimeout(dataUrl)

    const pdf = new jsPDF({
      orientation: img.width > img.height ? "landscape" : "portrait",
      unit: "mm",
      format: "a4",
    })

    const pageWidth = pdf.internal.pageSize.getWidth()
    const pageHeight = pdf.internal.pageSize.getHeight()

    await registerActivityPdfFont(pdf)

    pdf.setFontSize(14)
    pdf.text(title, 10, 12)
    pdf.setFontSize(8)
    pdf.text(new Date().toLocaleDateString(), 10, 17)

    const margin = 10
    const availableWidth = pageWidth - margin * 2
    const availableHeight = pageHeight - 25 - margin
    const scale = Math.min(availableWidth / img.width, availableHeight / img.height)
    const scaledWidth = img.width * scale
    const scaledHeight = img.height * scale

    pdf.addImage(dataUrl, "PNG", margin, 22, scaledWidth, scaledHeight)
    pdf.save(filename)
    return { success: true }
  } catch (err) {
    const message = err instanceof Error ? err.message : "PDF export failed"
    logError("[activityExport] PDF export failed:", message)
    return { success: false, error: message }
  }
}
