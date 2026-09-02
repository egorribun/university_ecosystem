/**
 * activityExport.ts — Multi-format export utilities for Activity page.
 * Follows scheduleExport.ts pattern (Wave 66). Dynamic imports only.
 */
import { logError } from "@/app/logger"
import i18n from "@/i18n/config"

export interface ExportResult {
  success: boolean
  error?: string
}

const IMAGE_LOAD_TIMEOUT_MS = 10_000

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
