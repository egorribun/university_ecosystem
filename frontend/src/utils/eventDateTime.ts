/**
 * Timezone-safe conversion helpers for event datetime-local fields.
 * These fields represent campus wall time; they are never parsed in the host
 * timezone. A changed wall value is accepted only when it identifies exactly
 * one instant in the configured IANA zone.
 */

export type EventDateFieldError =
  "required" | "invalid" | "nonexistent" | "ambiguous" | "timezoneUnavailable" | "endsBeforeStarts"

export type EventDateErrorTranslationKey =
  | "events:form.errors.startRequired"
  | "events:form.errors.endRequired"
  | "events:form.errors.endsBeforeStarts"
  | "events:form.errors.invalidDateTime"
  | "events:form.errors.nonexistentCampusTime"
  | "events:form.errors.ambiguousCampusTime"
  | "events:form.errors.campusTimezoneUnavailable"

export function eventDateErrorTranslationKey(
  error: EventDateFieldError,
  field: "start" | "end"
): EventDateErrorTranslationKey {
  if (error === "required") {
    return field === "start" ? "events:form.errors.startRequired" : "events:form.errors.endRequired"
  }
  if (error === "endsBeforeStarts") return "events:form.errors.endsBeforeStarts"
  if (error === "invalid") return "events:form.errors.invalidDateTime"
  if (error === "nonexistent") return "events:form.errors.nonexistentCampusTime"
  if (error === "ambiguous") return "events:form.errors.ambiguousCampusTime"
  return "events:form.errors.campusTimezoneUnavailable"
}

export type CampusWallTimeResult =
  | { status: "valid"; epochMilliseconds: number; iso: string }
  | { status: "invalid" | "nonexistent" | "ambiguous" }

export type EventDateRangeResolution = {
  startsAt: string | null
  endsAt: string | null
  startError: EventDateFieldError | null
  endError: EventDateFieldError | null
  valid: boolean
}

type DateTimeParts = {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
}

type OriginalEventTimes = {
  startsAt?: string | null
  endsAt?: string | null
}

const INPUT_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/
const HAS_EXPLICIT_OFFSET = /(?:Z|[+-]\d{2}:\d{2})$/i
const THREE_HOURS_MS = 3 * 60 * 60 * 1000
const OFFSET_SEARCH_RADIUS_MS = 36 * 60 * 60 * 1000

function createFormatter(timeZone: string): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat("en-US", {
    calendar: "gregory",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
    minute: "2-digit",
    month: "2-digit",
    numberingSystem: "latn",
    second: "2-digit",
    timeZone,
    year: "numeric",
  })
}

function readParts(formatter: Intl.DateTimeFormat, epochMilliseconds: number): DateTimeParts {
  const values = new Map(
    formatter.formatToParts(new Date(epochMilliseconds)).map(({ type, value }) => [type, value])
  )
  return {
    year: Number(values.get("year")),
    month: Number(values.get("month")),
    day: Number(values.get("day")),
    hour: Number(values.get("hour")),
    minute: Number(values.get("minute")),
    second: Number(values.get("second")),
  }
}

/** Build a UTC scalar without Date.UTC's special handling for years 0–99. */
function wallPartsToScalar(parts: DateTimeParts): number | null {
  if (
    parts.year < 1 ||
    parts.year > 9999 ||
    parts.month < 1 ||
    parts.month > 12 ||
    parts.day < 1 ||
    parts.hour < 0 ||
    parts.hour > 23 ||
    parts.minute < 0 ||
    parts.minute > 59 ||
    parts.second < 0 ||
    parts.second > 59
  ) {
    return null
  }

  const date = new Date(0)
  date.setUTCFullYear(parts.year, parts.month - 1, parts.day)
  date.setUTCHours(parts.hour, parts.minute, parts.second, 0)
  if (
    date.getUTCFullYear() !== parts.year ||
    date.getUTCMonth() + 1 !== parts.month ||
    date.getUTCDate() !== parts.day
  ) {
    return null
  }
  return date.getTime()
}

function parseWallInput(value: string): { parts: DateTimeParts; scalar: number } | null {
  const match = INPUT_PATTERN.exec(value)
  if (!match) return null
  const parts: DateTimeParts = {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
    second: 0,
  }
  const scalar = wallPartsToScalar(parts)
  return scalar === null ? null : { parts, scalar }
}

function partsMatch(left: DateTimeParts, right: DateTimeParts): boolean {
  return (
    left.year === right.year &&
    left.month === right.month &&
    left.day === right.day &&
    left.hour === right.hour &&
    left.minute === right.minute &&
    left.second === right.second
  )
}

/**
 * Resolve a campus wall time without host-zone interpretation or DST guessing.
 * Invalid calendar values, spring gaps, and fall folds are distinct outcomes.
 */
export function resolveCampusWallTime(value: string, timeZone: string): CampusWallTimeResult {
  const parsed = parseWallInput(value)
  if (!parsed) return { status: "invalid" }

  let formatter: Intl.DateTimeFormat
  try {
    formatter = createFormatter(timeZone)
  } catch {
    return { status: "invalid" }
  }

  const offsets = new Set<number>()
  for (
    let sample = parsed.scalar - OFFSET_SEARCH_RADIUS_MS;
    sample <= parsed.scalar + OFFSET_SEARCH_RADIUS_MS;
    sample += THREE_HOURS_MS
  ) {
    const local = readParts(formatter, sample)
    const localScalar = wallPartsToScalar(local)
    if (localScalar !== null) offsets.add(localScalar - sample)
  }

  const matches = new Set<number>()
  for (const offset of offsets) {
    const candidate = parsed.scalar - offset
    if (partsMatch(readParts(formatter, candidate), parsed.parts)) matches.add(candidate)
  }

  if (matches.size === 0) return { status: "nonexistent" }
  if (matches.size > 1) return { status: "ambiguous" }

  const epochMilliseconds = matches.values().next().value as number
  return { status: "valid", epochMilliseconds, iso: new Date(epochMilliseconds).toISOString() }
}

/** Format an instant for an HTML datetime-local field in the supplied zone. */
export function formatInstantForCampusInput(
  value: string | Date | null | undefined,
  timeZone: string | null
): string {
  if (!value || !timeZone) return ""
  if (typeof value === "string" && !HAS_EXPLICIT_OFFSET.test(value)) return ""
  const instant = value instanceof Date ? value : new Date(value)
  if (!Number.isFinite(instant.getTime())) return ""

  try {
    const parts = readParts(createFormatter(timeZone), instant.getTime())
    return `${String(parts.year).padStart(4, "0")}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}T${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`
  } catch {
    return ""
  }
}

/**
 * Display an unchanged API instant in campus wall time; values entered by the
 * datetime-local control are already wall values and pass through unchanged.
 */
export function formatEventDateInput(
  value: string | null | undefined,
  timeZone: string | null
): string {
  if (!value) return ""
  if (HAS_EXPLICIT_OFFSET.test(value)) return formatInstantForCampusInput(value, timeZone)
  return parseWallInput(value) ? value : ""
}

function resolveField(
  value: string,
  timeZone: string,
  original: string | null | undefined
): { instant: string; epochMilliseconds: number } | { error: EventDateFieldError } {
  if (!value) return { error: "required" }

  if (original) {
    const originalEpoch = HAS_EXPLICIT_OFFSET.test(original) ? Date.parse(original) : Number.NaN
    const originalInput = formatInstantForCampusInput(original, timeZone)
    if (Number.isFinite(originalEpoch) && (value === original || value === originalInput)) {
      return { instant: original, epochMilliseconds: originalEpoch }
    }
  }

  if (HAS_EXPLICIT_OFFSET.test(value)) {
    const epochMilliseconds = Date.parse(value)
    return Number.isFinite(epochMilliseconds)
      ? { instant: value, epochMilliseconds }
      : { error: "invalid" }
  }
  const resolution = resolveCampusWallTime(value, timeZone)
  if (resolution.status !== "valid") {
    return { error: resolution.status }
  }
  return { instant: resolution.iso, epochMilliseconds: resolution.epochMilliseconds }
}

/**
 * Validate/serialize the start and end wall values. Original API instants are
 * preserved when their displayed campus value is untouched, including fold
 * instants that could not be safely reconstructed from wall time alone.
 */
export function resolveCampusEventDateRange(
  startsAt: string,
  endsAt: string,
  timeZone: string | null,
  originals: OriginalEventTimes = {}
): EventDateRangeResolution {
  if (!timeZone) {
    return {
      startsAt: null,
      endsAt: null,
      startError: "timezoneUnavailable",
      endError: "timezoneUnavailable",
      valid: false,
    }
  }

  try {
    createFormatter(timeZone)
  } catch {
    return {
      startsAt: null,
      endsAt: null,
      startError: "timezoneUnavailable",
      endError: "timezoneUnavailable",
      valid: false,
    }
  }

  const start = resolveField(startsAt, timeZone, originals.startsAt)
  const end = resolveField(endsAt, timeZone, originals.endsAt)
  const startError = "error" in start ? start.error : null
  let endError = "error" in end ? end.error : null

  if (
    !startError &&
    !endError &&
    "epochMilliseconds" in start &&
    "epochMilliseconds" in end &&
    end.epochMilliseconds <= start.epochMilliseconds
  ) {
    endError = "endsBeforeStarts"
  }

  return {
    startsAt: "instant" in start ? start.instant : null,
    endsAt: "instant" in end ? end.instant : null,
    startError,
    endError,
    valid: !startError && !endError,
  }
}
