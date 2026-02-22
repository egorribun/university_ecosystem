/**
 * native date utility using Intl.DateTimeFormat and Intl.RelativeTimeFormat
 * to provide zero-bundle-size alternatives to dayjs.
 */

export type DateInput = Date | string | number

/**
 * Normalizes input to a Date object.
 */
export function toDate(input: DateInput): Date {
  if (input instanceof Date) return input
  return new Date(input)
}

/**
 * Basic formatting using Intl.DateTimeFormat.
 */
export function formatDate(input: DateInput, options: Intl.DateTimeFormatOptions = {}, locale = 'en-US'): string {
  const date = toDate(input)
  if (isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(locale, options).format(date)
}

/**
 * Precise format implementation for common app patterns.
 * Dayjs format strings replaced with native options.
 */
export const presets = {
  chatGroup: { month: 'long', day: 'numeric', year: 'numeric' } as Intl.DateTimeFormatOptions,
  chatTime: { hour: '2-digit', minute: '2-digit', hour12: false } as Intl.DateTimeFormatOptions,
  auditDate: { month: 'short', day: 'numeric' } as Intl.DateTimeFormatOptions,
  auditTime: { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false } as Intl.DateTimeFormatOptions,
  full: { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false } as Intl.DateTimeFormatOptions,
}

/**
 * Relative time formatting (e.g., "5 minutes ago", "in 2 days").
 */
export function formatRelativeTime(input: DateInput, locale = 'en-US'): string {
  const date = toDate(input)
  const now = new Date()
  const diffInSeconds = Math.floor((date.getTime() - now.getTime()) / 1000)

  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })

  const absSeconds = Math.abs(diffInSeconds)
  if (absSeconds < 60) return rtf.format(Math.sign(diffInSeconds) * absSeconds, 'second')
  const minutes = Math.floor(absSeconds / 60)
  if (minutes < 60) return rtf.format(Math.sign(diffInSeconds) * minutes, 'minute')
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return rtf.format(Math.sign(diffInSeconds) * hours, 'hour')
  const days = Math.floor(hours / 24)
  if (days < 30) return rtf.format(Math.sign(diffInSeconds) * days, 'day')
  const months = Math.floor(days / 30)
  return rtf.format(Math.sign(diffInSeconds) * months, 'month')
}

/**
 * Formats a date for use in <input type="datetime-local">.
 * Output: YYYY-MM-DDTHH:mm
 */
export function formatForInput(input: DateInput): string {
  const date = toDate(input)
  if (isNaN(date.getTime())) return ''

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')

  return `${year}-${month}-${day}T${hours}:${minutes}`
}

/**
 * Adds or subtracts units from a date.
 */
export function add(input: DateInput, count: number, unit: 'day' | 'hour' | 'minute' | 'month' | 'year'): Date {
  const date = new Date(toDate(input))
  switch (unit) {
    case 'year':
      date.setFullYear(date.getFullYear() + count)
      break
    case 'month':
      date.setMonth(date.getMonth() + count)
      break
    case 'day':
      date.setDate(date.getDate() + count)
      break
    case 'hour':
      date.setHours(date.getHours() + count)
      break
    case 'minute':
      date.setMinutes(date.getMinutes() + count)
      break
  }
  return date
}

/**
 * Moscow time formatting helper.
 */
export function getMoscowDate(input: DateInput): string {
  return formatDate(input, {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  })
}

/**
 * Helper to check if a date is after another.
 */
export function isAfter(a: DateInput, b: DateInput): boolean {
  return toDate(a).getTime() > toDate(b).getTime()
}

