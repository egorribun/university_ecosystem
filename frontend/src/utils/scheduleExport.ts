/**
 * scheduleExport.ts — Multi-format export utilities for schedule.
 * Wave 66 (Idea #9). Supports PDF, PNG, Google Calendar.
 *
 * FIX-67-EXPORT: Replaced html2canvas with html-to-image.
 * html2canvas can't parse CSS Color Level 4 `color()` function
 * (used by Tailwind v4). html-to-image uses SVG foreignObject —
 * the browser renders CSS natively, no parser issues.
 */
import {
  getEndTimeStr,
  getTimeStr,
  type Lesson,
  type WeekdayConfig,
} from "@/components/schedule/scheduleUtils"
import { getCampusClockParts, shiftCampusDateKey } from "@/utils/campusTimezone"
import { nowParity } from "@/utils/scheduleUtils"
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

export interface GoogleCalendarOccurrence {
  dateKey: string
  timeZone: string
}

type GoogleCalendarSelection =
  | { status: "ready"; lesson: Lesson; occurrence: GoogleCalendarOccurrence }
  | { status: "unavailable" | "empty" | "invalid-time" }

interface GoogleCalendarSelectionInput {
  schedule: readonly Lesson[]
  weekdayConfigs: readonly WeekdayConfig[]
  visibleWeekdays: readonly string[]
  selectedGroup: string | null
  now: Date
  weekOffset: number
  timeZone: string | null
  available: boolean
}

const CALENDAR_WEEKDAY_OFFSETS = new Map<string, number>([
  ["mon", 0],
  ["tue", 1],
  ["wed", 2],
  ["thu", 3],
  ["fri", 4],
  ["sat", 5],
  ["sun", 6],
])
const VALID_EXPORT_TIME = /^(?:[01]\d|2[0-3]):[0-5]\d$/
const VALID_EXPORT_DATE_KEY = /^\d{4}-\d{2}-\d{2}$/

export function selectGoogleCalendarLesson({
  schedule,
  weekdayConfigs,
  visibleWeekdays,
  selectedGroup,
  now,
  weekOffset,
  timeZone,
  available,
}: GoogleCalendarSelectionInput): GoogleCalendarSelection {
  if (!available || !selectedGroup?.trim() || !timeZone || !Number.isSafeInteger(weekOffset)) {
    return { status: "unavailable" }
  }

  const clock = getCampusClockParts(now, timeZone)
  if (!clock) return { status: "unavailable" }

  const dayOffset = weekOffset * 7 - ((clock.weekday + 6) % 7)
  const campusMidnight = Date.parse(`${clock.dateKey}T00:00:00Z`)
  const selectedMondayTime = campusMidnight + dayOffset * 86_400_000
  if (
    !Number.isSafeInteger(dayOffset) ||
    !Number.isFinite(selectedMondayTime) ||
    Math.abs(selectedMondayTime) > 8_640_000_000_000_000
  ) {
    return { status: "unavailable" }
  }

  const monday = shiftCampusDateKey(clock.dateKey, dayOffset)
  if (
    !VALID_EXPORT_DATE_KEY.test(monday) ||
    Date.parse(`${monday}T00:00:00Z`) !== selectedMondayTime
  ) {
    return { status: "unavailable" }
  }

  // UTC represents an explicit calendar key here, not the user's timezone.
  const occurrenceParity = nowParity(new Date(selectedMondayTime), "UTC")
  const offsets = new Map<string, number>()
  for (const config of weekdayConfigs) {
    const offset = CALENDAR_WEEKDAY_OFFSETS.get(config.id)
    if (offset === undefined) continue
    for (const backend of config.backend) offsets.set(backend, offset)
  }

  const candidates: Array<{ lesson: Lesson; rank: number; offset: number; start: string }> = []
  for (const lesson of schedule) {
    const rank = visibleWeekdays.indexOf(lesson.weekday)
    const offset = offsets.get(lesson.weekday)
    if (rank < 0 || offset === undefined) continue
    if (lesson.parity !== "both" && lesson.parity !== occurrenceParity) continue
    candidates.push({ lesson, rank, offset, start: getTimeStr(lesson) })
  }
  candidates.sort(
    (a, b) =>
      a.rank - b.rank ||
      a.start.localeCompare(b.start) ||
      (a.lesson.id < b.lesson.id ? -1 : a.lesson.id > b.lesson.id ? 1 : 0)
  )

  const first = candidates.at(0)
  if (!first) return { status: "empty" }
  if (first.lesson.group_id && first.lesson.group_id !== selectedGroup) {
    return { status: "unavailable" }
  }

  const end = getEndTimeStr(first.lesson)
  if (!VALID_EXPORT_TIME.test(first.start) || !VALID_EXPORT_TIME.test(end) || end <= first.start) {
    return { status: "invalid-time" }
  }

  const dateKey = shiftCampusDateKey(monday, first.offset)
  const occurrenceTime = Date.parse(`${dateKey}T00:00:00Z`)
  if (
    !VALID_EXPORT_DATE_KEY.test(dateKey) ||
    occurrenceTime !== selectedMondayTime + first.offset * 86_400_000
  ) {
    return { status: "unavailable" }
  }

  return {
    status: "ready",
    lesson: { ...first.lesson, start_time: first.start, end_time: end },
    occurrence: { dateKey, timeZone },
  }
}

/**
 * Generate a Google Calendar event creation URL for a lesson.
 * Opens in a new tab.
 */
export function generateGoogleCalendarUrl(
  lesson: Lesson,
  date: Date | GoogleCalendarOccurrence,
  labels?: ScheduleExportLabels
): string {
  const subject = lesson.subject ?? labels?.lessonFallback ?? "Lesson"
  const teacher = lesson.teacher ? ` (${lesson.teacher})` : ""
  const title = `${subject}${teacher}`
  const location = lesson.room ?? ""

  // Build date strings in Google Calendar format: YYYYMMDDTHHMMSS
  const startTime = date instanceof Date ? (lesson.start_time ?? "09:00") : getTimeStr(lesson)
  const endTime = date instanceof Date ? (lesson.end_time ?? "10:30") : getEndTimeStr(lesson)
  const [sh, sm] = startTime.split(":").map(Number)
  const [eh, em] = endTime.split(":").map(Number)

  let datePart: string
  if (date instanceof Date) {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, "0")
    const day = String(date.getDate()).padStart(2, "0")
    datePart = `${year}${month}${day}`
  } else {
    datePart = date.dateKey.replaceAll("-", "")
  }

  const startStr = `${datePart}T${String(sh).padStart(2, "0")}${String(sm).padStart(2, "0")}00`
  const endStr = `${datePart}T${String(eh).padStart(2, "0")}${String(em).padStart(2, "0")}00`

  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: title,
    dates: `${startStr}/${endStr}`,
    location,
    details: labels?.typePrefix
      ? labels.typePrefix.replace("{{type}}", lesson.lesson_type ?? "")
      : (lesson.lesson_type ?? ""),
  })

  if (!(date instanceof Date)) params.set("ctz", date.timeZone)

  return `https://calendar.google.com/calendar/r/eventedit?${params.toString()}`
}
