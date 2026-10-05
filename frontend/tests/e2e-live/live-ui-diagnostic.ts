const emittedRecords = new Set<string>()
const MAX_RECORDS = 16
const MAX_COUNT = 999
const MAX_DELTA_MILLI_PIXELS = 999_999

function safeCount(value: number): number | undefined {
  if (!Number.isSafeInteger(value) || value < 0) return undefined
  return Math.min(MAX_COUNT, value)
}

function safeDelta(value: number): number | undefined {
  if (!Number.isSafeInteger(value)) return undefined
  return Math.max(-MAX_DELTA_MILLI_PIXELS, Math.min(MAX_DELTA_MILLI_PIXELS, value))
}

function writeRecord(record: string): void {
  if (emittedRecords.size >= MAX_RECORDS || emittedRecords.has(record)) return
  emittedRecords.add(record)
  try {
    process.stdout.write(record)
  } catch {
    // Diagnostics must never replace the live acceptance assertion.
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
