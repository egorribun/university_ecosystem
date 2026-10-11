import {
  type Browser,
  type BrowserContext,
  type CDPSession,
  type Page,
  type TestInfo,
} from "@playwright/test"
import { readFileSync } from "node:fs"
import { isAbsolute, join } from "node:path"
import { ownedSessionOrigin, test as liveTest } from "./fixtures"

type Size = { width: number; height: number }
type StoryProjectUse = {
  acceptDownloads?: boolean
  actionTimeout?: number
  baseURL?: string
  clientCertificates?: unknown
  colorScheme?: null | string
  contrast?: null | string
  deviceScaleFactor?: number
  extraHTTPHeaders?: Record<string, string>
  forcedColors?: null | string
  hasTouch?: boolean
  ignoreHTTPSErrors?: boolean
  isMobile?: boolean
  locale?: string
  media?: string
  navigationTimeout?: number
  reducedMotion?: null | string
  screen?: Size
  serviceWorkers?: string
  userAgent?: string
  viewport?: Size | null
}
type PageState = {
  context: BrowserContext
  browserCdp: CDPSession
  mainTargetId: string
  pageSessions: Array<{ page: Page; session: CDPSession }>
}
type CleanupFailure = { step: string; error: unknown }

function throwFixtureOutcome(
  fixtureFailed: boolean,
  fixtureError: unknown,
  cleanupFailures: CleanupFailure[],
  cleanupMessage: string
): void {
  if (!fixtureFailed && cleanupFailures.length === 0) return

  const cleanupError =
    cleanupFailures.length > 0
      ? new AggregateError(
          cleanupFailures.map(({ step, error }) => {
            const wrapped = new Error(`Story cleanup failed at ${step}`)
            Object.assign(wrapped, { cause: error })
            return wrapped
          }),
          cleanupMessage
        )
      : undefined

  if (fixtureFailed && cleanupError) {
    throw new AggregateError(
      [fixtureError, cleanupError],
      `${cleanupMessage}; fixture work also failed`
    )
  }
  if (fixtureFailed) throw fixtureError
  if (cleanupError) throw cleanupError
}

const STORY_CHROMIUM_ARGS = [
  "--enable-automation",
  "--remote-debugging-port=0",
  "--no-startup-window",
  "--disable-background-networking",
]
const pageStates = new WeakMap<Page, PageState>()

function requiredSize(value: unknown, name: string): Size {
  if (typeof value !== "object" || value === null)
    throw new Error(`Story project ${name} is missing`)
  const size = value as Partial<Size>
  if (
    typeof size.width !== "number" ||
    !Number.isFinite(size.width) ||
    size.width < 1 ||
    typeof size.height !== "number" ||
    !Number.isFinite(size.height) ||
    size.height < 1
  ) {
    throw new Error(`Story project ${name} is invalid`)
  }
  return { width: size.width, height: size.height }
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || value.length === 0)
    throw new Error(`Story project ${name} is missing`)
  return value
}

function requiredTimeout(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`Story project ${name} is invalid`)
  }
  return value
}

function projectUse(testInfo: TestInfo): StoryProjectUse {
  const use = testInfo.project.use as StoryProjectUse
  const unsupportedOptions = [
    "bypassCSP",
    "clientCertificates",
    "geolocation",
    "httpCredentials",
    "offline",
    "permissions",
    "proxy",
    "storageState",
    "timezoneId",
    "javaScriptEnabled",
  ]
  for (const option of unsupportedOptions) {
    if (Reflect.get(use, option) !== undefined) {
      throw new Error(`Story CDP fixture does not support project option ${option}`)
    }
  }
  if (use.serviceWorkers !== undefined && use.serviceWorkers !== "allow") {
    throw new Error("Story CDP fixture requires the default service-worker policy")
  }
  if (use.acceptDownloads !== undefined && use.acceptDownloads !== true) {
    throw new Error("Story CDP fixture requires the default download policy")
  }
  for (const option of ["colorScheme", "contrast", "forcedColors", "reducedMotion"]) {
    if (Reflect.get(use, option) === null) {
      throw new Error(`Story CDP fixture does not support a null ${option} option`)
    }
  }
  const origin = ownedSessionOrigin()
  if (!use.baseURL || new URL(use.baseURL).origin !== origin) {
    throw new Error("Story project baseURL must match the owned live-stand origin")
  }
  if (typeof use.hasTouch !== "boolean" || typeof use.isMobile !== "boolean") {
    throw new Error("Story project must declare touch and mobile emulation")
  }
  if (typeof use.ignoreHTTPSErrors !== "boolean") {
    throw new Error("Story project must declare HTTPS error handling")
  }
  if (testInfo.project.name !== "desktop" && testInfo.project.name !== "mobile") {
    throw new Error("Story visibility proof requires a configured desktop or mobile project")
  }
  return use
}

function isAsciiDigitAt(value: string, index: number): boolean {
  const code = value.charCodeAt(index)
  return code >= 48 && code <= 57
}

function versionAfterMarker(
  userAgent: string,
  marker: string,
  separator: "." | "_",
  maxSegments: number,
  maxPrefixPadding = 0
): string | undefined {
  const markerIndex = userAgent.indexOf(marker)
  if (markerIndex < 0) return undefined

  let cursor = markerIndex + marker.length
  if (maxPrefixPadding > 0) {
    const paddingStart = cursor
    while (
      cursor < userAgent.length &&
      cursor - paddingStart < maxPrefixPadding &&
      !isAsciiDigitAt(userAgent, cursor)
    ) {
      cursor += 1
    }
    if (cursor === paddingStart || !isAsciiDigitAt(userAgent, cursor)) return undefined
  }

  const versionStart = cursor
  let versionEnd = cursor
  for (let segment = 0; segment < maxSegments; segment += 1) {
    const segmentStart = cursor
    while (
      cursor < userAgent.length &&
      cursor - segmentStart < 10 &&
      isAsciiDigitAt(userAgent, cursor)
    ) {
      cursor += 1
    }
    if (cursor === segmentStart) {
      return segment === 0 ? undefined : userAgent.slice(versionStart, versionEnd)
    }
    if (isAsciiDigitAt(userAgent, cursor)) return undefined

    versionEnd = cursor
    if (segment === maxSegments - 1 || userAgent[cursor] !== separator) {
      return userAgent.slice(versionStart, versionEnd)
    }
    cursor += 1
  }
  return userAgent.slice(versionStart, versionEnd)
}

function userAgentMetadata(userAgent: string, mobile: boolean) {
  const metadata = {
    mobile,
    model: "",
    architecture: "x86",
    platform: "Windows",
    platformVersion: "",
  }
  const androidVersion = versionAfterMarker(userAgent, "Android ", ".", 3)
  const iPhoneVersion = versionAfterMarker(userAgent, "iPhone OS ", "_", 2)
  const iPadVersion = versionAfterMarker(userAgent, "iPad; CPU OS ", "_", 2)
  const macOSVersion = versionAfterMarker(userAgent, "Mac OS X ", "_", 3)
  const windowsVersion = versionAfterMarker(userAgent, "Windows", ".", 3, 32)
  if (androidVersion) {
    metadata.platform = "Android"
    metadata.platformVersion = androidVersion
    metadata.architecture = "arm"
  } else if (iPhoneVersion || iPadVersion) {
    metadata.platform = "iOS"
    metadata.platformVersion = iPhoneVersion ?? iPadVersion ?? ""
    metadata.architecture = "arm"
  } else if (macOSVersion) {
    metadata.platform = "macOS"
    metadata.platformVersion = macOSVersion
    if (!userAgent.includes("Intel")) metadata.architecture = "arm"
  } else if (windowsVersion) {
    metadata.platform = "Windows"
    metadata.platformVersion = windowsVersion
  } else if (userAgent.toLowerCase().includes("linux")) {
    metadata.platform = "Linux"
  }
  if (userAgent.includes("ARM")) metadata.architecture = "arm"
  return metadata
}
function profileDirectory(arguments_: string[]): string {
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index]
    if (argument?.startsWith("--user-data-dir=")) return argument.slice("--user-data-dir=".length)
    if (argument === "--user-data-dir" && typeof arguments_[index + 1] === "string") {
      return arguments_[index + 1] as string
    }
  }
  throw new Error("Managed Chromium command line did not expose its temporary user-data-dir")
}

async function waitForDebuggingPort(profile: string): Promise<number> {
  if (!isAbsolute(profile)) throw new Error("Managed Chromium profile path must be absolute")
  const portFile = join(profile, "DevToolsActivePort")
  const deadline = Date.now() + 3_000
  while (Date.now() < deadline) {
    try {
      const port = Number(readFileSync(portFile, "utf8").trim().split(/\r?\n/u)[0])
      if (Number.isSafeInteger(port) && port > 0) return port
    } catch {
      // The browser creates DevToolsActivePort after its process is ready.
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  throw new Error("Timed out waiting for the managed Chromium DevToolsActivePort")
}

async function applyProjectOptions(
  page: Page,
  session: CDPSession,
  testInfo: TestInfo,
  origin: string
): Promise<void> {
  const use = projectUse(testInfo)
  const viewport = requiredSize(use.viewport, "viewport")
  // Playwright 1.63 defaults screen to viewport when no screen is configured.
  const screen = use.screen === undefined ? viewport : requiredSize(use.screen, "screen")
  const deviceScaleFactor = use.deviceScaleFactor
  if (
    typeof deviceScaleFactor !== "number" ||
    !Number.isFinite(deviceScaleFactor) ||
    deviceScaleFactor <= 0
  ) {
    throw new Error("Story project deviceScaleFactor is invalid")
  }
  const userAgent = requiredString(use.userAgent, "userAgent")
  const locale = requiredString(use.locale, "locale")
  const actionTimeout = requiredTimeout(use.actionTimeout, "actionTimeout")
  const navigationTimeout = requiredTimeout(use.navigationTimeout, "navigationTimeout")
  if (actionTimeout !== 15_000 || navigationTimeout !== 45_000) {
    throw new Error("Story project action and navigation timeouts differ from the live lane")
  }
  const mobile = use.isMobile as boolean

  await session.send("Emulation.setFocusEmulationEnabled", { enabled: false })
  await session.send("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor,
    mobile,
    screenWidth: screen.width,
    screenHeight: screen.height,
    screenOrientation: mobile
      ? screen.width > screen.height
        ? { angle: 90, type: "landscapePrimary" }
        : { angle: 0, type: "portraitPrimary" }
      : { angle: 0, type: "landscapePrimary" },
  })
  await session.send("Emulation.setTouchEmulationEnabled", {
    enabled: use.hasTouch as boolean,
  })
  await session.send("Emulation.setUserAgentOverride", {
    userAgent,
    acceptLanguage: locale,
    userAgentMetadata: userAgentMetadata(userAgent, mobile),
  })
  await session.send("Emulation.setLocaleOverride", { locale })
  const mediaFeatures = [
    // These defaults match the pinned Playwright 1.63 browser-context options.
    { name: "prefers-color-scheme", value: use.colorScheme ?? "light" },
    { name: "prefers-reduced-motion", value: use.reducedMotion ?? "no-preference" },
    { name: "forced-colors", value: use.forcedColors ?? "none" },
    { name: "prefers-contrast", value: use.contrast ?? "no-preference" },
  ]
  await session.send("Emulation.setEmulatedMedia", {
    media: use.media ?? "",
    features: mediaFeatures,
  })
  if (use.ignoreHTTPSErrors) {
    await session.send("Security.setIgnoreCertificateErrors", { ignore: true })
  }
  if (use.extraHTTPHeaders) {
    await session.send("Network.setExtraHTTPHeaders", { headers: use.extraHTTPHeaders })
  }
  page.setDefaultTimeout(actionTimeout)
  page.setDefaultNavigationTimeout(navigationTimeout)
  if (new URL(use.baseURL as string).origin !== origin) {
    throw new Error("Story project baseURL changed while applying its options")
  }
}

export const storyVisibilityTest = liveTest.extend<{ storyBrowser: Browser; page: Page }>({
  storyBrowser: async ({ browserName, launchOptions, playwright }, runFixture) => {
    if (browserName !== "chromium") throw new Error("Story visibility proof requires Chromium")
    const launchArgs = launchOptions.args ?? []
    if (
      launchArgs.some((argument) =>
        /^--(?:user-data-dir|remote-debugging-port)(?:=|$)/u.test(argument)
      )
    ) {
      throw new Error(
        "Story visibility fixture requires a managed temporary Chromium profile and port"
      )
    }
    // A fresh managed launch gives each Story test its own temporary profile and default context.
    const owner = await playwright.chromium.launch({
      ...launchOptions,
      handleSIGINT: false,
      channel: "chromium",
      headless: true,
      args: [...launchArgs, ...STORY_CHROMIUM_ARGS],
    })
    let fixtureError: unknown
    let fixtureFailed = false
    const cleanupFailures: CleanupFailure[] = []
    try {
      await runFixture(owner)
    } catch (error) {
      fixtureError = error
      fixtureFailed = true
    }
    try {
      await owner.close()
    } catch (error) {
      cleanupFailures.push({ step: "owner-close", error })
    }
    try {
      if (owner.isConnected()) {
        cleanupFailures.push({
          step: "owner-connected-after-close",
          error: new Error("Managed Story Chromium remained connected after close"),
        })
      }
    } catch (error) {
      cleanupFailures.push({ step: "owner-connection-check", error })
    }
    throwFixtureOutcome(
      fixtureFailed,
      fixtureError,
      cleanupFailures,
      "Managed Story Chromium fixture cleanup failed"
    )
  },
  page: async ({ storyBrowser, browserName, playwright }, runFixture, testInfo) => {
    if (browserName !== "chromium") throw new Error("Story visibility proof requires Chromium")
    if (storyBrowser.contexts().length !== 0) {
      throw new Error("Managed Story browser unexpectedly has an existing Playwright context")
    }

    let ownerCdp: CDPSession | undefined
    let attached: Browser | undefined
    let browserCdp: CDPSession | undefined
    let context: BrowserContext | undefined
    const pageSessions: Array<{ page: Page; session: CDPSession }> = []
    const cleanupFailures: CleanupFailure[] = []
    let fixtureError: unknown
    let fixtureFailed = false
    try {
      ownerCdp = await storyBrowser.newBrowserCDPSession()
      const commandLine = (await ownerCdp.send("Browser.getBrowserCommandLine")) as {
        arguments?: unknown
      }
      if (
        !Array.isArray(commandLine.arguments) ||
        commandLine.arguments.some((item) => typeof item !== "string")
      ) {
        throw new Error("Managed Chromium command line response is invalid")
      }
      const port = await waitForDebuggingPort(profileDirectory(commandLine.arguments as string[]))
      attached = await playwright.chromium.connectOverCDP(`http://127.0.0.1:${port}`, {
        // Standard Playwright CDP defaults install visible-capture emulation that masks real tab hiding.
        noDefaults: true,
        isLocal: true,
        timeout: 3_000,
      })
      const contexts = attached.contexts()
      if (contexts.length !== 1)
        throw new Error("Expected exactly one managed Chromium default context")
      context = contexts[0]
      if (!context) throw new Error("The managed Chromium default context is unavailable")
      if (context.pages().length !== 0) {
        throw new Error("Managed Chromium default context contains a page before Story setup")
      }
      browserCdp = await attached.newBrowserCDPSession()

      const origin = ownedSessionOrigin()
      await context.clearCookies()
      if ((await context.cookies(origin)).length !== 0) {
        throw new Error("Owned-origin cookies leaked into Story test setup")
      }

      const [page, target] = await Promise.all([
        context.waitForEvent("page", { timeout: 3_000 }),
        browserCdp.send("Target.createTarget", {
          url: "about:blank",
          newWindow: true,
          background: false,
        }),
      ])
      const mainTargetId = (target as { targetId?: unknown }).targetId
      if (typeof mainTargetId !== "string" || mainTargetId.length === 0) {
        throw new Error("Managed Chromium did not return the Story main target id")
      }
      if (context.pages().length !== 1 || context.pages()[0] !== page) {
        throw new Error("Managed Chromium main target did not create exactly one Story page")
      }
      const pageCdp = await context.newCDPSession(page)
      pageSessions.push({ page, session: pageCdp })
      await applyProjectOptions(page, pageCdp, testInfo, origin)
      pageStates.set(page, {
        context,
        browserCdp,
        mainTargetId,
        pageSessions,
      })
      await runFixture(page)
    } catch (error) {
      fixtureError = error
      fixtureFailed = true
    }

    for (const { page, session } of pageSessions) {
      try {
        if (page.isClosed()) continue
        await session.detach()
      } catch (error) {
        cleanupFailures.push({ step: "page-CDP-session", error })
      }
    }
    let pagesToClose: Page[] = []
    try {
      pagesToClose = context?.pages() ?? []
    } catch (error) {
      cleanupFailures.push({ step: "context-pages", error })
    }
    for (const page of pagesToClose) {
      try {
        await page.close()
      } catch (error) {
        cleanupFailures.push({ step: "page-close", error })
      }
    }
    if (browserCdp) {
      try {
        await browserCdp.detach()
      } catch (error) {
        cleanupFailures.push({ step: "browser-CDP-session", error })
      }
    }
    if (attached) {
      try {
        await attached.close()
      } catch (error) {
        cleanupFailures.push({ step: "CDP-disconnect", error })
      }
      try {
        if (attached.isConnected()) {
          cleanupFailures.push({
            step: "CDP-connection-remained-open",
            error: new Error("Story CDP attachment remained connected after close"),
          })
        }
      } catch (error) {
        cleanupFailures.push({ step: "CDP-connection-check", error })
      }
      try {
        if (!storyBrowser.isConnected()) {
          cleanupFailures.push({
            step: "owner-browser-closed-by-CDP-disconnect",
            error: new Error("Disconnecting the Story CDP attachment closed its owner browser"),
          })
        }
      } catch (error) {
        cleanupFailures.push({ step: "owner-connection-check", error })
      }
    }
    if (ownerCdp) {
      try {
        await ownerCdp.detach()
      } catch (error) {
        cleanupFailures.push({ step: "owner-CDP-session", error })
      }
    }
    throwFixtureOutcome(
      fixtureFailed,
      fixtureError,
      cleanupFailures,
      "Story CDP fixture cleanup failed"
    )
  },
})

export async function openStoryBackgroundTab(mainPage: Page): Promise<Page> {
  const state = pageStates.get(mainPage)
  if (!state) throw new Error("Story main page is not owned by the Story visibility fixture")
  const [backgroundPage, target] = await Promise.all([
    state.context.waitForEvent("page", { timeout: 3_000 }),
    state.browserCdp.send("Target.createTarget", {
      url: "about:blank",
      newWindow: false,
      // Create an actual background tab in the existing browser window.
      background: true,
    }),
  ])
  const targetId = (target as { targetId?: unknown }).targetId
  if (typeof targetId !== "string" || targetId.length === 0) {
    await backgroundPage.close()
    throw new Error("Managed Chromium did not return the Story pause target id")
  }
  if (state.context.pages().length !== 2 || !state.context.pages().includes(backgroundPage)) {
    await backgroundPage.close()
    throw new Error("Managed Chromium did not add exactly one Story pause tab")
  }
  const session = await state.context.newCDPSession(backgroundPage)
  state.pageSessions.push({ page: backgroundPage, session })
  await session.send("Emulation.setFocusEmulationEnabled", { enabled: false })
  const [mainWindow, backgroundWindow] = await Promise.all([
    state.browserCdp.send("Browser.getWindowForTarget", { targetId: state.mainTargetId }),
    state.browserCdp.send("Browser.getWindowForTarget", { targetId }),
  ])
  const mainWindowId = (mainWindow as { windowId?: unknown }).windowId
  const backgroundWindowId = (backgroundWindow as { windowId?: unknown }).windowId
  if (
    typeof mainWindowId !== "number" ||
    !Number.isSafeInteger(mainWindowId) ||
    typeof backgroundWindowId !== "number" ||
    !Number.isSafeInteger(backgroundWindowId) ||
    mainWindowId !== backgroundWindowId
  ) {
    await backgroundPage.close()
    throw new Error("Story pause tab was not created in the main page's browser window")
  }
  return backgroundPage
}
