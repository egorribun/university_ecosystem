const emittedRecords = new Set<string>()
const MAX_RECORDS = 16
const MAX_A11Y_CONTRAST_RECORDS = 16
const MAX_A11Y_CONTRAST_RECORDS_PER_ROUTE = 4
const MAX_COUNT = 999
const MAX_DELTA_MILLI_PIXELS = 999_999
const HEX_COLOR_PATTERN = /^#[0-9a-f]{6}$/iu
const emittedA11yContrastRecords = new Set<string>()
const emittedA11yContrastByRoute = new Map<string, Set<string>>()

function safeCount(value: number): number | undefined {
  if (!Number.isSafeInteger(value) || value < 0) return undefined
  return Math.min(MAX_COUNT, value)
}

function safeDelta(value: number): number | undefined {
  if (!Number.isSafeInteger(value)) return undefined
  return Math.max(-MAX_DELTA_MILLI_PIXELS, Math.min(MAX_DELTA_MILLI_PIXELS, value))
}

function writeRecord(
  record: string,
  records: Set<string> = emittedRecords,
  maximum = MAX_RECORDS
): boolean {
  if (records.size >= maximum || records.has(record)) return false
  records.add(record)
  try {
    process.stdout.write(record)
    return true
  } catch {
    // Diagnostics must never replace the live acceptance assertion.
    return false
  }
}

export function reportLiveAdminQueueState(
  project: string,
  status: number,
  itemsAreArray: boolean,
  itemCount: number,
  totalIsInteger: boolean,
  tableVisible: boolean,
  progressbarVisible: boolean,
  alertVisible: boolean,
  rowCount: number
): void {
  const safeItems = safeCount(itemCount)
  const safeRows = safeCount(rowCount)
  if (
    (project !== "desktop" && project !== "mobile") ||
    !Number.isInteger(status) ||
    (status !== 0 && (status < 100 || status > 599)) ||
    typeof itemsAreArray !== "boolean" ||
    safeItems === undefined ||
    typeof totalIsInteger !== "boolean" ||
    typeof tableVisible !== "boolean" ||
    typeof progressbarVisible !== "boolean" ||
    typeof alertVisible !== "boolean" ||
    safeRows === undefined
  ) {
    return
  }

  writeRecord(
    `UE_LIVE_ADMIN_QUEUE_V1 project=${project} status=${status} items_array=${itemsAreArray} items_count=${safeItems} total_valid=${totalIsInteger} table_visible=${tableVisible} progressbar_visible=${progressbarVisible} alert_visible=${alertVisible} row_count=${safeRows}\n`
  )
}

function safeContrastColor(value: unknown): string | undefined {
  if (typeof value !== "string" || value.length !== 7 || !HEX_COLOR_PATTERN.test(value)) {
    return undefined
  }
  return value.toLowerCase()
}

function safeContrastRatioMilli(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 21) {
    return undefined
  }
  return Math.round(value * 1000)
}

export function reportLiveAxeColorContrast(
  project: string,
  route: string,
  foreground: unknown,
  background: unknown,
  contrastRatio: unknown
): void {
  const safeForeground = safeContrastColor(foreground)
  const safeBackground = safeContrastColor(background)
  const safeRatio = safeContrastRatioMilli(contrastRatio)
  if (
    (project !== "desktop" && project !== "mobile") ||
    (route !== "dashboard" && route !== "settings") ||
    safeForeground === undefined ||
    safeBackground === undefined ||
    safeRatio === undefined
  ) {
    return
  }

  const routeKey = `${project}/${route}`
  let routeRecords = emittedA11yContrastByRoute.get(routeKey)
  if (routeRecords === undefined) {
    routeRecords = new Set<string>()
    emittedA11yContrastByRoute.set(routeKey, routeRecords)
  }
  const record =
    `UE_LIVE_A11Y_CONTRAST_V1 project=${project} route=${route} ` +
    `fg=${safeForeground} bg=${safeBackground} ratio_milli=${safeRatio}\n`
  if (routeRecords.size >= MAX_A11Y_CONTRAST_RECORDS_PER_ROUTE || routeRecords.has(record)) {
    return
  }
  if (writeRecord(record, emittedA11yContrastRecords, MAX_A11Y_CONTRAST_RECORDS)) {
    routeRecords.add(record)
  }
}

export function reportLiveActivityGeometry(
  project: string,
  period: string,
  indicatorPresent: boolean,
  radioPresent: boolean,
  dxMilliPixels: number,
  dyMilliPixels: number,
  dwMilliPixels: number,
  dhMilliPixels: number
): void {
  const dx = safeDelta(dxMilliPixels)
  const dy = safeDelta(dyMilliPixels)
  const dw = safeDelta(dwMilliPixels)
  const dh = safeDelta(dhMilliPixels)
  if (
    (project !== "desktop" && project !== "mobile") ||
    (period !== "30-day" && period !== "90-day") ||
    typeof indicatorPresent !== "boolean" ||
    typeof radioPresent !== "boolean" ||
    dx === undefined ||
    dy === undefined ||
    dw === undefined ||
    dh === undefined
  ) {
    return
  }

  writeRecord(
    `UE_LIVE_ACTIVITY_GEOMETRY_V1 project=${project} period=${period} indicator_present=${indicatorPresent} radio_present=${radioPresent} dx_milli=${dx} dy_milli=${dy} dw_milli=${dw} dh_milli=${dh}\n`
  )
}
