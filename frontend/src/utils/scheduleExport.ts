/**
 * scheduleExport.ts — Multi-format export utilities for schedule.
 * Wave 66 (Idea #9). Supports PDF, PNG, Google Calendar.
 */
import type { Lesson } from "@/components/schedule/scheduleUtils"

/**
 * Export schedule grid as PNG image.
 * Dynamically imports html2canvas to keep bundle size small.
 */
export async function exportScheduleAsPng(
  gridElement: HTMLElement,
  filename = "schedule.png",
): Promise<void> {
  const { default: html2canvas } = await import("html2canvas")
  const canvas = await html2canvas(gridElement, {
    backgroundColor: null,
    scale: 2,
    useCORS: true,
    logging: false,
  })
  const url = canvas.toDataURL("image/png")
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
}

/**
 * Export schedule grid as PDF document.
 * Dynamically imports html2canvas + jspdf.
 */
export async function exportScheduleAsPdf(
  gridElement: HTMLElement,
  title = "Расписание",
  filename = "schedule.pdf",
): Promise<void> {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import("html2canvas"),
    import("jspdf"),
  ])

  const canvas = await html2canvas(gridElement, {
    backgroundColor: "#0f172a", // dark bg for consistent rendering
    scale: 2,
    useCORS: true,
    logging: false,
  })

  const imgData = canvas.toDataURL("image/png")
  const imgWidth = canvas.width
  const imgHeight = canvas.height

  // A4 landscape for wide schedule grids
  const pdf = new jsPDF({
    orientation: imgWidth > imgHeight ? "landscape" : "portrait",
    unit: "mm",
    format: "a4",
  })

  const pageWidth = pdf.internal.pageSize.getWidth()
  const pageHeight = pdf.internal.pageSize.getHeight()

  // Title
  pdf.setFontSize(14)
  pdf.text(title, 10, 12)
  pdf.setFontSize(8)
  pdf.text(new Date().toLocaleDateString("ru-RU"), 10, 17)

  // Scale image to fit page with margins
  const margin = 10
  const availableWidth = pageWidth - margin * 2
  const availableHeight = pageHeight - 25 - margin // 25mm for header
  const scale = Math.min(availableWidth / imgWidth, availableHeight / imgHeight)
  const scaledWidth = imgWidth * scale
  const scaledHeight = imgHeight * scale

  pdf.addImage(imgData, "PNG", margin, 22, scaledWidth, scaledHeight)
  pdf.save(filename)
}

/**
 * Generate a Google Calendar event creation URL for a lesson.
 * Opens in a new tab.
 */
export function generateGoogleCalendarUrl(lesson: Lesson, date: Date): string {
  const subject = lesson.subject ?? "Занятие"
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
    details: `Тип: ${lesson.lesson_type ?? ""}`,
  })

  return `https://calendar.google.com/calendar/r/eventedit?${params.toString()}`
}
