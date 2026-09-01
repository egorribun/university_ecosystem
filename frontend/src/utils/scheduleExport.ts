/**
 * scheduleExport.ts — Multi-format export utilities for schedule.
 * Wave 66 (Idea #9). Supports PDF, PNG, Google Calendar.
 *
 * FIX-67-EXPORT: Replaced html2canvas with html-to-image.
 * html2canvas can't parse CSS Color Level 4 `color()` function
 * (used by Tailwind v4). html-to-image uses SVG foreignObject —
 * the browser renders CSS natively, no parser issues.
 */
import type { Lesson } from "@/components/schedule/scheduleUtils"
import { logError } from "@/app/logger"
import i18n from "@/i18n/config"

export interface ExportResult {
  success: boolean
  error?: string
}

const IMAGE_LOAD_TIMEOUT_MS = 10_000

/** Load an image from dataUrl with a timeout to prevent hangs (FIX-68-01). */
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

/**
 * Export schedule grid as PNG image.
 * Dynamically imports html-to-image to keep bundle size small.
 */
export async function exportScheduleAsPng(
  gridElement: HTMLElement,
  filename = "schedule.png"
): Promise<ExportResult> {
  try {
    const { toPng } = await import("html-to-image")
    const dataUrl = await toPng(gridElement, { pixelRatio: 2, skipFonts: true })
    const a = document.createElement("a")
    a.href = dataUrl
    a.download = filename
    a.click()
    return { success: true }
  } catch (err) {
    const message = err instanceof Error ? err.message : "PNG export failed"
    logError("[scheduleExport] PNG export failed:", message)
    return { success: false, error: message }
  }
}

/**
 * Export schedule grid as PDF document.
 * Dynamically imports html-to-image + jspdf.
 */
export interface ScheduleExportLabels {
  title?: string
  lessonFallback?: string
  typePrefix?: string
}

export async function exportScheduleAsPdf(
  gridElement: HTMLElement,
  title = i18n.t("schedule:title.default"),
  filename = "schedule.pdf"
): Promise<ExportResult> {
  try {
    const [{ toPng }, { jsPDF }] = await Promise.all([import("html-to-image"), import("jspdf")])

    const dataUrl = await toPng(gridElement, { pixelRatio: 2, skipFonts: true })

    // Load image with timeout to prevent hangs (FIX-68-01)
    const img = await loadImageWithTimeout(dataUrl)

    // A4 landscape for wide schedule grids
    const pdf = new jsPDF({
      orientation: img.width > img.height ? "landscape" : "portrait",
      unit: "mm",
      format: "a4",
    })

    const pageWidth = pdf.internal.pageSize.getWidth()
    const pageHeight = pdf.internal.pageSize.getHeight()

    // Title
    pdf.setFontSize(14)
    pdf.text(title, 10, 12)
    pdf.setFontSize(8)
    pdf.text(new Date().toLocaleDateString(), 10, 17)

    // Scale image to fit page with margins
    const margin = 10
    const availableWidth = pageWidth - margin * 2
    const availableHeight = pageHeight - 25 - margin // 25mm for header
    const scale = Math.min(availableWidth / img.width, availableHeight / img.height)
    const scaledWidth = img.width * scale
    const scaledHeight = img.height * scale

    pdf.addImage(dataUrl, "PNG", margin, 22, scaledWidth, scaledHeight)
    pdf.save(filename)
    return { success: true }
  } catch (err) {
    const message = err instanceof Error ? err.message : "PDF export failed"
    logError("[scheduleExport] PDF export failed:", message)
    return { success: false, error: message }
  }
}

/**
 * Generate a Google Calendar event creation URL for a lesson.
 * Opens in a new tab.
 */
export function generateGoogleCalendarUrl(
  lesson: Lesson,
  date: Date,
  labels?: ScheduleExportLabels
): string {
  const subject = lesson.subject ?? labels?.lessonFallback ?? "Lesson"
  const teacher = lesson.teacher ? ` (${lesson.teacher})` : ""
  const title = `${subject}${teacher}`
  const location = lesson.room ?? ""

  // Build date strings in Google Calendar format: YYYYMMDDTHHMMSS
  const startTime = lesson.start_time ?? "09:00"
  const endTime = lesson.end_time ?? "10:30"
  const [sh, sm] = startTime.split(":").map(Number)
  const [eh, em] = endTime.split(":").map(Number)

  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, "0")
  const d = String(date.getDate()).padStart(2, "0")

  const startStr = `${y}${m}${d}T${String(sh).padStart(2, "0")}${String(sm).padStart(2, "0")}00`
  const endStr = `${y}${m}${d}T${String(eh).padStart(2, "0")}${String(em).padStart(2, "0")}00`

  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: title,
    dates: `${startStr}/${endStr}`,
    location,
    details: labels?.typePrefix
      ? labels.typePrefix.replace("{{type}}", lesson.lesson_type ?? "")
      : (lesson.lesson_type ?? ""),
  })

  return `https://calendar.google.com/calendar/r/eventedit?${params.toString()}`
}
