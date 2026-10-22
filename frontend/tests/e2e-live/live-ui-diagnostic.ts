const emittedRecords = new Set<string>()
const MAX_RECORDS = 16
const MAX_A11Y_CONTRAST_RECORDS = 16
const MAX_A11Y_CONTRAST_RECORDS_PER_ROUTE = 4
const MAX_COUNT = 999
const MAX_DELTA_MILLI_PIXELS = 999_999
const HEX_COLOR_PATTERN = /^#[0-9a-f]{6}$/iu
const A11Y_TEXT_COLOR_TAGS = new Set(["opaque", "translucent", "transparent"])
const A11Y_OPACITY_TAGS = new Set([
  "none",
  "node",
  "ancestor",
  "fade",
  "layout",
  "fade-pending",
  "multiple",
])
const A11Y_ANIMATION_TAGS = new Set(["none", "opacity", "transform", "color", "other", "mixed"])
const A11Y_PHASE_LABELS = new Set(["before_axe", "after_axe"])
const MAX_A11Y_PHASE_RECORDS = 16
const emittedA11yPhaseRecords = new Set<string>()
const emittedA11yPhaseByRoute = new Map<string, Set<string>>()
const emittedA11yContrastRecords = new Set<string>()
const emittedA11yContrastByRoute = new Map<string, Set<string>>()
const MAX_A11Y_PAINT_RECORDS = 16
const MAX_FOOTER_GEOMETRY_RECORDS = 16
const MAX_DIAGNOSTIC_PIXEL_MILLI = 5_000_000
const emittedA11yPaintRecords = new Set<string>()
const emittedA11yPaintByRoute = new Map<string, Set<string>>()
const emittedFooterGeometryRecords = new Set<string>()

function safeCount(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) return undefined
  return Math.min(MAX_COUNT, value)
}

function safeDelta(value: number): number | undefined {
  if (!Number.isSafeInteger(value)) return undefined
  return Math.max(-MAX_DELTA_MILLI_PIXELS, Math.min(MAX_DELTA_MILLI_PIXELS, value))
}

function safeOpacityMilli(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    return undefined
  }
  return Math.round(value * 1000)
}

function safePixelMilli(value: unknown): number | undefined {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    Math.abs(value) > MAX_DIAGNOSTIC_PIXEL_MILLI / 1000
  ) {
    return undefined
  }
  return Math.round(value * 1000)
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

function safeFixedTag(value: unknown, allowed: ReadonlySet<string>): string | undefined {
  return typeof value === "string" && allowed.has(value) ? value : undefined
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

export function reportLiveAxePaintState(
  project: string,
  route: string,
  axeForeground: unknown,
  axeBackground: unknown,
  contrastRatio: unknown,
  computedForeground: unknown,
  textColorTag: unknown,
  computedForegroundAlpha: unknown,
  nodeOpacity: unknown,
  ancestorOpacity: unknown,
  opacityTag: unknown,
  pageFadeReady: unknown,
  pageFadeOpacity: unknown,
  layoutOpacity: unknown,
  animationTag: unknown,
  activeAnimations: unknown
): void {
  const safeAxeForeground = safeContrastColor(axeForeground)
  const safeAxeBackground = safeContrastColor(axeBackground)
  const safeRatio = safeContrastRatioMilli(contrastRatio)
  const safeComputedForeground = safeContrastColor(computedForeground)
  const safeTextColorTag = safeFixedTag(textColorTag, A11Y_TEXT_COLOR_TAGS)
  const safeOpacityTag = safeFixedTag(opacityTag, A11Y_OPACITY_TAGS)
  const safeAnimationTag = safeFixedTag(animationTag, A11Y_ANIMATION_TAGS)
  const safeComputedAlpha = safeOpacityMilli(computedForegroundAlpha)
  const safeNodeOpacity = safeOpacityMilli(nodeOpacity)
  const safeAncestorOpacity = safeOpacityMilli(ancestorOpacity)
  const safePageOpacity = safeOpacityMilli(pageFadeOpacity)
  const safeLayoutOpacity = safeOpacityMilli(layoutOpacity)
  const safeAnimations = safeCount(activeAnimations)
  if (
    (project !== "desktop" && project !== "mobile") ||
    (route !== "dashboard" && route !== "settings") ||
    safeAxeForeground === undefined ||
    safeAxeBackground === undefined ||
    safeRatio === undefined ||
    safeComputedForeground === undefined ||
    safeTextColorTag === undefined ||
    safeOpacityTag === undefined ||
    safeAnimationTag === undefined ||
    safeComputedAlpha === undefined ||
    safeNodeOpacity === undefined ||
    safeAncestorOpacity === undefined ||
    typeof pageFadeReady !== "boolean" ||
    safePageOpacity === undefined ||
    safeLayoutOpacity === undefined ||
    safeAnimations === undefined
  ) {
    return
  }

  const routeKey = `${project}/${route}`
  let routeRecords = emittedA11yPaintByRoute.get(routeKey)
  if (routeRecords === undefined) {
    routeRecords = new Set<string>()
    emittedA11yPaintByRoute.set(routeKey, routeRecords)
  }
  const record =
    `UE_LIVE_A11Y_PAINT_V1 project=${project} route=${route} ` +
    `axe_fg=${safeAxeForeground} axe_bg=${safeAxeBackground} ratio_milli=${safeRatio} ` +
    `css_fg=${safeComputedForeground} text_color=${safeTextColorTag} ` +
    `css_alpha_milli=${safeComputedAlpha} node_opacity_milli=${safeNodeOpacity} ` +
    `ancestor_opacity_milli=${safeAncestorOpacity} opacity_tag=${safeOpacityTag} ` +
    `page_ready=${pageFadeReady} page_opacity_milli=${safePageOpacity} ` +
    `layout_opacity_milli=${safeLayoutOpacity} animation=${safeAnimationTag} ` +
    `active_animations=${safeAnimations}\n`
  if (routeRecords.size >= 4 || routeRecords.has(record)) return
  if (writeRecord(record, emittedA11yPaintRecords, MAX_A11Y_PAINT_RECORDS)) {
    routeRecords.add(record)
  }
}

export function reportLiveA11yPhaseState(
  project: string,
  route: string,
  phase: unknown,
  pageFadeReady: unknown,
  pageFadeOpacity: unknown,
  rootOpacity: unknown,
  layoutOpacity: unknown,
  animationTag: unknown,
  activeAnimations: unknown
): void {
  const safePhase = safeFixedTag(phase, A11Y_PHASE_LABELS)
  const safePageOpacity = safeOpacityMilli(pageFadeOpacity)
  const safeRootOpacity = safeOpacityMilli(rootOpacity)
  const safeLayoutOpacity = safeOpacityMilli(layoutOpacity)
  const safeAnimation = safeFixedTag(animationTag, A11Y_ANIMATION_TAGS)
  const safeAnimations = safeCount(activeAnimations)
  if (
    (project !== "desktop" && project !== "mobile") ||
    (route !== "dashboard" && route !== "settings") ||
    safePhase === undefined ||
    typeof pageFadeReady !== "boolean" ||
    safePageOpacity === undefined ||
    safeRootOpacity === undefined ||
    safeLayoutOpacity === undefined ||
    safeAnimation === undefined ||
    safeAnimations === undefined
  ) {
    return
  }

  const routeKey = project + "/" + route
  let routePhases = emittedA11yPhaseByRoute.get(routeKey)
  if (routePhases === undefined) {
    routePhases = new Set<string>()
    emittedA11yPhaseByRoute.set(routeKey, routePhases)
  }
  if (routePhases.has(safePhase)) return
  const record =
    `UE_LIVE_A11Y_PHASE_V1 project=${project} route=${route} phase=${safePhase} ` +
    `page_ready=${pageFadeReady} page_opacity_milli=${safePageOpacity} ` +
    `root_opacity_milli=${safeRootOpacity} layout_opacity_milli=${safeLayoutOpacity} ` +
    `animation=${safeAnimation} active_animations=${safeAnimations}\n`
  if (writeRecord(record, emittedA11yPhaseRecords, MAX_A11Y_PHASE_RECORDS)) {
    routePhases.add(safePhase)
  }
}
export function reportLiveFooterGeometry(
  project: string,
  requestedWidth: unknown,
  requestedHeight: unknown,
  innerWidth: unknown,
  innerHeight: unknown,
  clientWidth: unknown,
  scrollWidth: unknown,
  navLeft: unknown,
  navRight: unknown,
  navTop: unknown,
  navBottom: unknown,
  navWidth: unknown,
  navTransformPresent: unknown,
  navTransformX: unknown,
  navTransformY: unknown,
  fixedContainingBlockFound: unknown,
  fixedContainingBlockDepth: unknown,
  containingBlockLeft: unknown,
  containingBlockRight: unknown,
  containingBlockTop: unknown,
  containingBlockBottom: unknown
): void {
  const pixels = [
    requestedWidth,
    requestedHeight,
    innerWidth,
    innerHeight,
    clientWidth,
    scrollWidth,
    navLeft,
    navRight,
    navTop,
    navBottom,
    navWidth,
    navTransformX,
    navTransformY,
    containingBlockLeft,
    containingBlockRight,
    containingBlockTop,
    containingBlockBottom,
  ].map(safePixelMilli)
  const depth = safeCount(fixedContainingBlockDepth)
  if (
    (project !== "desktop" && project !== "mobile") ||
    pixels.some((value) => value === undefined) ||
    pixels[0]! <= 0 ||
    pixels[1]! <= 0 ||
    pixels[2]! <= 0 ||
    pixels[3]! <= 0 ||
    pixels[4]! < 0 ||
    pixels[5]! < 0 ||
    pixels[10]! < 0 ||
    typeof navTransformPresent !== "boolean" ||
    typeof fixedContainingBlockFound !== "boolean" ||
    depth === undefined ||
    depth > 32 ||
    (fixedContainingBlockFound
      ? depth === 0
      : depth !== 0 || pixels.slice(13).some((value) => value !== 0))
  ) {
    return
  }

  const [
    requestedWidthMilli,
    requestedHeightMilli,
    innerWidthMilli,
    innerHeightMilli,
    clientWidthMilli,
    scrollWidthMilli,
    navLeftMilli,
    navRightMilli,
    navTopMilli,
    navBottomMilli,
    navWidthMilli,
    navTransformXMilli,
    navTransformYMilli,
    containingBlockLeftMilli,
    containingBlockRightMilli,
    containingBlockTopMilli,
    containingBlockBottomMilli,
  ] = pixels as number[]
  const record =
    `UE_LIVE_FOOTER_GEOM_V1 project=${project} req_w_milli=${requestedWidthMilli} ` +
    `req_h_milli=${requestedHeightMilli} inner_w_milli=${innerWidthMilli} ` +
    `inner_h_milli=${innerHeightMilli} client_w_milli=${clientWidthMilli} ` +
    `scroll_w_milli=${scrollWidthMilli} nav_left_milli=${navLeftMilli} ` +
    `nav_right_milli=${navRightMilli} nav_top_milli=${navTopMilli} ` +
    `nav_bottom_milli=${navBottomMilli} nav_width_milli=${navWidthMilli} ` +
    `nav_transform_present=${navTransformPresent} nav_tx_milli=${navTransformXMilli} ` +
    `nav_ty_milli=${navTransformYMilli} fixed_cb_found=${fixedContainingBlockFound} ` +
    `fixed_cb_depth=${depth} cb_left_milli=${containingBlockLeftMilli} ` +
    `cb_right_milli=${containingBlockRightMilli} cb_top_milli=${containingBlockTopMilli} ` +
    `cb_bottom_milli=${containingBlockBottomMilli}\n`
  writeRecord(record, emittedFooterGeometryRecords, MAX_FOOTER_GEOMETRY_RECORDS)
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

const emittedPasswordResetRegistrationRecords = new Set<string>()

export function reportLivePasswordResetRegistrationFailure(project: string, step: string): void {
  if (
    (project !== "desktop" && project !== "mobile") ||
    (step !== "arm-response" && step !== "click" && step !== "await-response")
  ) {
    return
  }

  writeRecord(
    `UE_LIVE_RESET_REGISTRATION_V1 project=${project} step=${step}\n`,
    emittedPasswordResetRegistrationRecords,
    6
  )
}
