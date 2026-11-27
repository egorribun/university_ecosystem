import { randomUUID } from "node:crypto"
import { lstatSync, rmSync, type Stats } from "node:fs"
import { lstat, mkdtemp, readFile, realpath, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { basename, dirname, isAbsolute, join, parse, relative, resolve } from "node:path"
import {
  removeBeforeCleanupDeadline,
  withVerifiedNativePushBrowserExit,
} from "./native-push-profile-cleanup"
import { test as liveTest, ownedSessionOrigin, liveDeadlineBoundedTimeoutMs } from "./fixtures"
import { readPlaywrightTestSlotDeadlineAtMs } from "../../scripts/live-registration-admission.mjs"
import {
  createLivePushFailureObservation,
  reportLivePushDeliveryObservation,
} from "./push-delivery-observation"
import type {
  Browser,
  BrowserContext,
  BrowserContextOptions,
  Page,
  TestInfo,
  ViewportSize,
} from "@playwright/test"

const PROFILE_PREFIX = "ue-live-native-push-"
const PROFILE_OWNER_MARKER = ".ue-live-native-push-owner"
const PROFILE_CLOSE_TIMEOUT_MS = 10_000
const PROFILE_CLEANUP_TIMEOUT_MS = 30_000

export function livePushObservationBudgetMs(
  testInfo: TestInfo,
  cleanupReserveMs = PROFILE_CLEANUP_TIMEOUT_MS
): number {
  if (!Number.isFinite(cleanupReserveMs) || cleanupReserveMs < 0) return 0
  // The topic delivery scenario uses a 360-second slot, supported by this
  // shared adapter even though the rate-limit retry wrapper caps slots at 180 seconds.
  let deadlineAtMs: number | null
  try {
    deadlineAtMs = readPlaywrightTestSlotDeadlineAtMs(testInfo)
  } catch {
    return 0
  }
  if (deadlineAtMs === null) return 0
  return liveDeadlineBoundedTimeoutMs(deadlineAtMs - cleanupReserveMs, 1_200) ?? 0
}

/**
 * Live Web Push subscriptions need the branded Google Chrome build with its push
 * service. Playwright's open-source Chromium fails `pushManager.subscribe` with
 * "push service not available", and off-the-record contexts fail with
 * "permission denied", so push-subscribing specs must use this persistent profile.
 */
export const NATIVE_PUSH_BROWSER_CHANNEL = "chrome"

export type NativePushProfile = {
  context: BrowserContext
  page: Page
}

export type NativePushProfileRegistry = {
  primary: NativePushProfile
  create: () => Promise<NativePushProfile>
  armFailureObservation: (
    expectedTag: string,
    onCapture?: () => Promise<void>
  ) => ReturnType<typeof createLivePushFailureObservation>
}

type NativePushProfileFixtures = {
  nativePushProfiles: NativePushProfileRegistry
}

type NativePushProfileOptions = {
  nativePushChannel: string | undefined
}

type DirectoryIdentity = {
  dev: number
  ino: number
  birthtimeMs: number
}

type OwnedProfile = {
  path: string
  root: string
  marker: string
  markerValue: string
  identity: DirectoryIdentity
  context?: BrowserContext
  browser?: Browser
  disconnected: Promise<void>
  disconnectObserved: boolean
}

function identityOf(stat: Stats): DirectoryIdentity {
  return { dev: stat.dev, ino: stat.ino, birthtimeMs: stat.birthtimeMs }
}

function sameIdentity(left: DirectoryIdentity, right: DirectoryIdentity): boolean {
  return left.dev === right.dev && left.ino === right.ino && left.birthtimeMs === right.birthtimeMs
}

async function assertNoReparseAncestors(path: string): Promise<void> {
  let current = resolve(path)
  const root = parse(current).root
  if (!root || !isAbsolute(current)) throw new Error("Push profile path is not absolute")
  while (true) {
    const stat = await lstat(current)
    if (stat.isSymbolicLink() || !stat.isDirectory()) {
      throw new Error("Push profile path contains a non-directory or reparse point")
    }
    if (current === root) return
    const parent = dirname(current)
    if (parent === current) throw new Error("Push profile path ancestry is invalid")
    current = parent
  }
}

async function canonicalTemporaryRoot(): Promise<string> {
  const root = await realpath(tmpdir())
  if (!isAbsolute(root) || root.startsWith("\\\\")) {
    throw new Error("Push profile temporary root must be a local absolute directory")
  }
  await assertNoReparseAncestors(root)
  return root
}

/**
 * Chrome's own notification centre instead of the operating system's. Under
 * automation the system path closes every notification at once (headless and
 * headful, Windows and Linux), so getNotifications() could never observe a
 * real Web Push. The notifications stay real Chrome notifications with their
 * tags; only the display surface changes.
 */
/**
 * Budget for the subscription save that follows an explicit opt-in, and for any
 * save created before that click. It covers Chrome's registration with the real
 * FCM push service: 3-6 s on a local stand, above the 15 s action timeout on
 * some hosted runs (live run 43457859398).
 */
export const PUSH_SUBSCRIBE_SAVE_TIMEOUT_MS = 60_000

/**
 * Bound for one native Web Push notification to reach the recipient service
 * worker. FCM delivery to Chrome took longer than 60 s on hosted runs even after
 * the provider accepted the push, so the owner raised this bound to 120 s
 * (2026-11-26). The poll still requires exactly one notification with the
 * persisted identity.
 */
export const NATIVE_PUSH_NOTIFICATION_WAIT_MS = 120_000

/**
 * Minimum test budget for a spec that drives a real native Push profile. Such a
 * test waits on a subscription save (60 s) and a native delivery poll
 * (NATIVE_PUSH_NOTIFICATION_WAIT_MS) besides account setup and cleanup, so the
 * suite-wide 60 s test timeout cannot hold the step budgets it declares: on hosted
 * runs where FCM registration is slow, the test timed out inside a bounded step.
 * Each step keeps its own bound; a spec may still set a larger budget itself.
 */
export const NATIVE_PUSH_TEST_TIMEOUT_MS = 240_000

export const NATIVE_PUSH_BROWSER_ARGS = ["--disable-features=NativeNotifications"] as const

function contextOptionsForProject(
  testInfo: TestInfo,
  channel: string | undefined
): BrowserContextOptions & { channel?: string; headless: boolean; args: string[] } {
  const projectUse = testInfo.project.use
  const configuredViewport = projectUse.viewport as ViewportSize | undefined
  if (
    !configuredViewport ||
    !Number.isSafeInteger(configuredViewport.width) ||
    !Number.isSafeInteger(configuredViewport.height) ||
    configuredViewport.width < 1 ||
    configuredViewport.height < 1
  ) {
    throw new Error("Native Push profile requires the configured project viewport")
  }

  const options: BrowserContextOptions & {
    channel?: string
    headless: boolean
    args: string[]
  } = {
    baseURL: ownedSessionOrigin(),
    ignoreHTTPSErrors: true,
    locale: typeof projectUse.locale === "string" ? projectUse.locale : "ru-RU",
    viewport: { ...configuredViewport },
    headless: true,
    args: [...NATIVE_PUSH_BROWSER_ARGS],
  }
  if (typeof projectUse.deviceScaleFactor === "number") {
    options.deviceScaleFactor = projectUse.deviceScaleFactor
  }
  if (typeof projectUse.isMobile === "boolean") options.isMobile = projectUse.isMobile
  if (typeof projectUse.hasTouch === "boolean") options.hasTouch = projectUse.hasTouch
  if (typeof projectUse.userAgent === "string") options.userAgent = projectUse.userAgent
  if (typeof channel === "string") options.channel = channel
  return options
}

async function createOwnedProfile(
  browser: Browser,
  testInfo: TestInfo,
  channel: string | undefined,
  records: OwnedProfile[]
): Promise<NativePushProfile> {
  const root = await canonicalTemporaryRoot()
  const profilePath = await mkdtemp(join(root, PROFILE_PREFIX))
  const canonicalProfilePath = await realpath(profilePath)
  const relativePath = relative(root, canonicalProfilePath)
  if (
    dirname(canonicalProfilePath) !== root ||
    !relativePath ||
    relativePath === "." ||
    relativePath.startsWith("..") ||
    relativePath.includes("/") ||
    relativePath.includes("\\") ||
    basename(canonicalProfilePath) !== relativePath
  ) {
    throw new Error("Native Push profile is not a unique direct child of the temporary root")
  }

  const stat = await lstat(canonicalProfilePath, { bigint: false })
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error("Native Push profile directory identity could not be established")
  }
  const markerValue = randomUUID()
  const marker = join(canonicalProfilePath, PROFILE_OWNER_MARKER)
  const record: OwnedProfile = {
    path: canonicalProfilePath,
    root,
    marker,
    markerValue,
    identity: identityOf(stat),
    disconnected: Promise.resolve(),
    disconnectObserved: false,
  }
  records.push(record)
  await writeFile(marker, markerValue, { encoding: "utf8", flag: "wx", mode: 0o600 })

  const context = await browser
    .browserType()
    .launchPersistentContext(canonicalProfilePath, contextOptionsForProject(testInfo, channel))
  record.context = context
  const ownedBrowser = context.browser()
  if (!ownedBrowser) {
    throw new Error("Native Push profile browser identity could not be verified")
  }
  record.browser = ownedBrowser
  let resolveDisconnected: () => void = () => undefined
  record.disconnected = new Promise<void>((resolveDisconnectedPromise) => {
    resolveDisconnected = resolveDisconnectedPromise
  })
  ownedBrowser.once("disconnected", () => {
    record.disconnectObserved = true
    resolveDisconnected()
  })
  if (!ownedBrowser.isConnected()) {
    throw new Error("Native Push profile browser identity could not be verified")
  }

  const page = await context.newPage()
  const actionTimeout = testInfo.project.use.actionTimeout
  const navigationTimeout = testInfo.project.use.navigationTimeout
  page.setDefaultTimeout(typeof actionTimeout === "number" ? actionTimeout : 15_000)
  page.setDefaultNavigationTimeout(
    typeof navigationTimeout === "number" ? navigationTimeout : 45_000
  )
  return { context, page }
}

async function withTimeout<T>(operation: Promise<T>, timeoutMs: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(
      () => reject(new Error("Native Push profile cleanup deadline expired")),
      timeoutMs
    )
  })
  try {
    return await Promise.race([operation, timeout])
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

async function verifyProfileBeforeRemoval(record: OwnedProfile): Promise<string> {
  const context = record.context
  if (!context) {
    throw new Error("Native Push profile has no recorded context owner; profile preserved")
  }

  return withVerifiedNativePushBrowserExit(
    {
      context,
      browser: record.browser,
      disconnected: record.disconnected,
      disconnectObserved: () => record.disconnectObserved,
      withTimeout,
      timeoutMs: PROFILE_CLOSE_TIMEOUT_MS,
    },
    async () => {
      const canonicalPath = await realpath(record.path)
      if (canonicalPath !== record.path || dirname(canonicalPath) !== record.root) {
        throw new Error("Native Push profile path changed; profile preserved")
      }
      await assertNoReparseAncestors(canonicalPath)
      const stat = await lstat(canonicalPath, { bigint: false })
      if (
        stat.isSymbolicLink() ||
        !stat.isDirectory() ||
        !sameIdentity(identityOf(stat), record.identity)
      ) {
        throw new Error("Native Push profile identity changed; profile preserved")
      }
      const markerStat = await lstat(record.marker)
      if (markerStat.isSymbolicLink() || !markerStat.isFile()) {
        throw new Error("Native Push profile owner marker changed; profile preserved")
      }
      if ((await readFile(record.marker, "utf8")) !== record.markerValue) {
        throw new Error("Native Push profile owner marker did not match; profile preserved")
      }
      return canonicalPath
    }
  )
}

function removeVerifiedProfile(canonicalPath: string): void {
  rmSync(canonicalPath, { recursive: true, force: false, maxRetries: 0 })
  try {
    lstatSync(canonicalPath)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return
    throw error
  }
  throw new Error("Native Push profile remains after exact cleanup")
}

export const test = liveTest.extend<NativePushProfileFixtures & NativePushProfileOptions>({
  nativePushChannel: [NATIVE_PUSH_BROWSER_CHANNEL, { option: true }],
  nativePushProfiles: async ({ browser, nativePushChannel }, provideFixture, testInfo) => {
    // A zero timeout means "unbounded" and stays so; a smaller budget is raised.
    if (testInfo.timeout !== 0 && testInfo.timeout < NATIVE_PUSH_TEST_TIMEOUT_MS) {
      testInfo.setTimeout(NATIVE_PUSH_TEST_TIMEOUT_MS)
    }
    const records: OwnedProfile[] = []
    let testFailure: unknown
    let testFailed = false
    try {
      const primary = await createOwnedProfile(browser, testInfo, nativePushChannel, records)
      let pendingFailureObservation: ReturnType<typeof createLivePushFailureObservation> | undefined
      const registry: NativePushProfileRegistry = {
        primary,
        create: () => createOwnedProfile(browser, testInfo, nativePushChannel, records),
        armFailureObservation: (expectedTag, onCapture) => {
          if (pendingFailureObservation?.isArmed()) {
            throw new Error("Native Push failure observation is already armed")
          }
          const observation = createLivePushFailureObservation(async () => {
            // The additional recipient observation shares the established
            // browser diagnostic's window instead of extending it serially.
            await Promise.all([
              reportLivePushDeliveryObservation(primary.page, testInfo.project.name, expectedTag),
              onCapture?.(),
            ])
          })
          pendingFailureObservation = observation
          return observation
        },
      }
      await provideFixture(registry)

      await pendingFailureObservation?.captureIfAborted(testInfo.status)
    } catch (error) {
      testFailure = error
      testFailed = true
    }

    const cleanupFailures: string[] = []
    for (const record of [...records].reverse()) {
      try {
        const cleanupDeadline = Date.now() + PROFILE_CLEANUP_TIMEOUT_MS
        const canonicalPath = await withTimeout(
          verifyProfileBeforeRemoval(record),
          PROFILE_CLEANUP_TIMEOUT_MS
        )
        // Keep final removal synchronous and outside the timeout race: fs promises are not cancellable.
        removeBeforeCleanupDeadline(cleanupDeadline, () => removeVerifiedProfile(canonicalPath))
      } catch {
        cleanupFailures.push("owned-profile-cleanup")
      }
    }
    if (cleanupFailures.length > 0) {
      const cleanupFailure = new Error(
        "One or more owned native Push profiles could not be verified and removed"
      )
      if (testFailed) throw new AggregateError([testFailure, cleanupFailure])
      throw cleanupFailure
    }
    if (testFailed) throw testFailure
  },
  ownedSessionCleanup: async ({ nativePushProfiles, ownedSessionCleanup }, provideFixture) => {
    // This dependency keeps the inherited session fixture teardown after profile setup.
    // The plain override preserves the base fixture's automatic scope and timeout.
    void nativePushProfiles
    await provideFixture(ownedSessionCleanup)
  },
  page: async ({ nativePushProfiles }, provideFixture) => {
    // Keep the inherited pageErrors auto fixture attached to the real profile page.
    await provideFixture(nativePushProfiles.primary.page)
  },
})
