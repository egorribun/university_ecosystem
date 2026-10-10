import { randomUUID } from "node:crypto"
import { lstatSync, rmSync, type Stats } from "node:fs"
import { lstat, mkdtemp, readFile, realpath, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { basename, dirname, isAbsolute, join, parse, relative, resolve } from "node:path"
import {
  removeBeforeCleanupDeadline,
  withVerifiedNativePushBrowserExit,
} from "./native-push-profile-cleanup"
import { test as liveTest, ownedSessionOrigin } from "./fixtures"
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

export type NativePushProfile = {
  context: BrowserContext
  page: Page
}

export type NativePushProfileRegistry = {
  primary: NativePushProfile
  create: () => Promise<NativePushProfile>
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

function contextOptionsForProject(
  testInfo: TestInfo,
  channel: string | undefined
): BrowserContextOptions & { channel?: string; headless: boolean } {
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

  const options: BrowserContextOptions & { channel?: string; headless: boolean } = {
    baseURL: ownedSessionOrigin(),
    ignoreHTTPSErrors: true,
    locale: typeof projectUse.locale === "string" ? projectUse.locale : "ru-RU",
    viewport: { ...configuredViewport },
    headless: true,
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
  nativePushChannel: [undefined, { option: true }],
  nativePushProfiles: async ({ browser, nativePushChannel }, provideFixture, testInfo) => {
    const records: OwnedProfile[] = []
    let testFailure: unknown
    let testFailed = false
    try {
      const primary = await createOwnedProfile(browser, testInfo, nativePushChannel, records)
      const registry: NativePushProfileRegistry = {
        primary,
        create: () => createOwnedProfile(browser, testInfo, nativePushChannel, records),
      }
      await provideFixture(registry)
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
