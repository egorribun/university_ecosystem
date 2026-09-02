import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type MotionProps = Record<string, unknown> & { children?: ReactNode }
type TranslationCall = { key: string; options?: Record<string, unknown> }
type TransCall = { i18nKey: string; components?: Record<string, ReactNode> }
type PushPrefs = {
  topicKeys: string[]
  topicState: Record<string, boolean>
  pushSupported: boolean
  notificationPermission: NotificationPermission
  notificationsEnabled: boolean
  pushBusy: boolean
  pushInitializing: boolean
  permissionText: string
  enableNotifications: () => Promise<void>
  disableNotifications: () => Promise<void>
  handleTopicToggle: (key: string) => () => void
  safariIOS: boolean
  safariGuideUrl: string
}

const state = vi.hoisted(() => ({
  motionCalls: [] as MotionProps[],
  translationCalls: [] as TranslationCall[],
  transCalls: [] as TransCall[],
  mediaQueries: [] as string[],
  standalone: false,
  minimalUi: false,
  navigatorStandalone: undefined as boolean | undefined,
  onNotify: null as ((toast: unknown) => void) | null,
  pushPrefs: null as PushPrefs | null,
}))

vi.mock("framer-motion", async () => {
  const base = (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
  const baseMotionDiv = base.m.div
  if (!baseMotionDiv) throw new Error("framer-motion mock must expose m.div")
  const captureMotionDiv = (props: MotionProps) => {
    state.motionCalls.push(props)
    return baseMotionDiv(props)
  }
  const capturedMotion = new Proxy(base.m as object, {
    get(target, property, receiver) {
      if (property === "div") return captureMotionDiv
      return Reflect.get(target, property, receiver)
    },
  }) as typeof base.m

  return { ...base, m: capturedMotion, motion: capturedMotion }
})

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: string | string[]) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      state.translationCalls.push({ key, options })
      return typeof options?.appName === "string" ? `${key} ${options.appName}` : key
    },
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    // Keep this side effect in the hook body so namespace mutations are observable.
    ...(() => {
      state.translationCalls.push({
        key: "__namespace__",
        options: { namespaces },
      })
      return {}
    })(),
  }),
  Trans: (props: TransCall) => {
    state.transCalls.push(props)
    return props.i18nKey
  },
}))

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: (options?: { onNotify?: (toast: unknown) => void }) => {
    state.onNotify = options?.onNotify ?? null
    if (!state.pushPrefs) throw new Error("push preferences fixture was not initialized")
    return state.pushPrefs
  },
}))

import InstallPrompt from "@/components/pwa/InstallPrompt"
import { PWA_REFRESH_EVENT } from "@/app/pwaEvents"

const INSTALL_DISMISS_KEY = "ecosystem.pwa.install.dismissedAt"
const PUSH_DISMISS_KEY = "ecosystem.push.education.dismissedAt"
const DISMISS_TTL = 7 * 24 * 60 * 60 * 1000

function createPushPrefs(overrides: Partial<PushPrefs> = {}): PushPrefs {
  return {
    topicKeys: ["schedule", "news"],
    topicState: { schedule: true, news: false },
    pushSupported: true,
    notificationPermission: "default",
    notificationsEnabled: false,
    pushBusy: false,
    pushInitializing: false,
    permissionText: "default",
    enableNotifications: vi.fn(() => Promise.resolve()),
    disableNotifications: vi.fn(() => Promise.resolve()),
    handleTopicToggle: vi.fn(() => vi.fn()),
    safariIOS: false,
    safariGuideUrl: "https://support.apple.com/guide",
    ...overrides,
  }
}

function configureBrowserSurface(): void {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn((query: string) => {
      state.mediaQueries.push(query)
      return {
        matches:
          query === "(display-mode: standalone)"
            ? state.standalone
            : query === "(display-mode: minimal-ui)"
              ? state.minimalUi
              : false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }
    }),
  })

  if (state.navigatorStandalone === undefined) {
    Reflect.deleteProperty(window.navigator, "standalone")
  } else {
    Object.defineProperty(window.navigator, "standalone", {
      configurable: true,
      value: state.navigatorStandalone,
    })
  }
}

type PromptEvent = Event & {
  prompt: ReturnType<typeof vi.fn>
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
}

function makePromptEvent(
  outcome: "accepted" | "dismissed" = "accepted",
  prompt: ReturnType<typeof vi.fn> = vi.fn(() => Promise.resolve())
): PromptEvent {
  const event = new Event("beforeinstallprompt") as PromptEvent
  event.prompt = prompt
  event.userChoice = Promise.resolve({ outcome })
  return event
}

async function firePrompt(
  outcome: "accepted" | "dismissed" = "accepted",
  prompt?: ReturnType<typeof vi.fn>
): Promise<PromptEvent> {
  const event = makePromptEvent(outcome, prompt)
  await act(async () => {
    window.dispatchEvent(event)
    await Promise.resolve()
  })
  return event
}

function findMotionCall(predicate: (call: MotionProps) => boolean): MotionProps | undefined {
  return state.motionCalls.find(predicate)
}

function findPromptRoot(): HTMLElement {
  const root = document.querySelector(".fixed.bottom-24")
  if (!(root instanceof HTMLElement)) throw new Error("install prompt root was not rendered")
  return root
}

function findPanelContent(root: HTMLElement): HTMLElement {
  const panel = Array.from(root.querySelectorAll("div")).find((element) => {
    const className = String(element.className)
    return className.includes("flex flex-col") && className.includes("gap-")
  })
  if (!(panel instanceof HTMLElement)) throw new Error("install prompt content was not rendered")
  return panel
}

beforeEach(() => {
  state.motionCalls.length = 0
  state.translationCalls.length = 0
  state.transCalls.length = 0
  state.mediaQueries.length = 0
  state.standalone = false
  state.minimalUi = false
  state.navigatorStandalone = undefined
  state.onNotify = null
  state.pushPrefs = createPushPrefs()
  window.localStorage.clear()
  vi.stubEnv("VITE_LHCI", "")
  configureBrowserSurface()
})

afterEach(() => {
  vi.unstubAllEnvs()
  window.localStorage.clear()
  Reflect.deleteProperty(window.navigator, "standalone")
})

describe("InstallPrompt mutation contracts", () => {
  it("keeps all install, feedback, and update motion variants intact", async () => {
    render(<InstallPrompt />)
    const installVariants = await waitFor(() => {
      const call = findMotionCall((entry) => String(entry.className).includes("fixed bottom-24"))
      if (!call) throw new Error("install motion call not captured")
      return call
    })
    expect(installVariants.variants).toEqual({
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    })

    await act(async () => {
      state.onNotify?.({ text: "saved", severity: "success" })
      await Promise.resolve()
    })
    const feedback = findMotionCall((entry) => String(entry.className).includes("top-24"))
    expect(feedback).toMatchObject({
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    })

    const update = vi.fn(() => Promise.resolve())
    await act(async () => {
      window.dispatchEvent(new CustomEvent(PWA_REFRESH_EVENT, { detail: { update } }))
      await Promise.resolve()
    })
    const updateToast = findMotionCall((entry) => String(entry.className).includes("max-w-[28rem]"))
    expect(updateToast).toMatchObject({
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    })
  })

  it("uses both display-mode media queries and the navigator standalone flag", async () => {
    state.standalone = true
    const standaloneRender = render(<InstallPrompt />)
    await firePrompt()
    expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    expect(state.mediaQueries).toContain("(display-mode: standalone)")
    standaloneRender.unmount()

    state.standalone = false
    state.minimalUi = true
    state.mediaQueries.length = 0
    const minimalRender = render(<InstallPrompt />)
    await firePrompt()
    expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    expect(state.mediaQueries).toEqual(["(display-mode: standalone)", "(display-mode: minimal-ui)"])
    minimalRender.unmount()

    state.standalone = false
    state.minimalUi = false
    state.navigatorStandalone = true
    configureBrowserSurface()
    const navigatorRender = render(<InstallPrompt />)
    await firePrompt()
    expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    navigatorRender.unmount()
  })

  it("does not parse an absent dismissal timestamp", () => {
    const finiteSpy = vi.spyOn(Number, "isFinite")
    try {
      render(<InstallPrompt />)
      expect(finiteSpy).not.toHaveBeenCalled()
    } finally {
      finiteSpy.mockRestore()
    }
  })

  it("registers and removes every lifecycle listener on unmount", () => {
    const removeSpy = vi.spyOn(window, "removeEventListener")
    const { unmount } = render(<InstallPrompt />)
    unmount()

    expect(removeSpy).toHaveBeenCalledWith(PWA_REFRESH_EVENT, expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith("beforeinstallprompt", expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith("appinstalled", expect.any(Function))
    removeSpy.mockRestore()
  })

  it("clears an install prompt and its persisted timestamp after appinstalled", async () => {
    render(<InstallPrompt />)
    await firePrompt()
    expect(screen.getByText(/system:installPrompt\.installTitle/)).toBeInTheDocument()
    window.localStorage.setItem(INSTALL_DISMISS_KEY, String(Date.now()))

    await act(async () => {
      window.dispatchEvent(new Event("appinstalled"))
      await Promise.resolve()
    })
    expect(screen.queryByText(/system:installPrompt\.installTitle/)).not.toBeInTheDocument()
    expect(window.localStorage.getItem(INSTALL_DISMISS_KEY)).toBeNull()
  })

  it("keeps the install button disabled while prompt() is pending and re-enables it", async () => {
    let resolvePrompt!: () => void
    const prompt = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolvePrompt = resolve
        })
    )
    const user = userEvent.setup()
    render(<InstallPrompt />)
    await firePrompt("accepted", prompt)
    const installButton = screen.getByRole("button", { name: "system:installPrompt.install" })

    const choice = Promise.resolve({ outcome: "accepted" as const })
    const pendingEvent = makePromptEvent("accepted", prompt)
    pendingEvent.userChoice = choice
    await user.click(installButton)
    expect(installButton).toBeDisabled()

    resolvePrompt()
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })

    await firePrompt()
    expect(screen.getByRole("button", { name: "system:installPrompt.install" })).not.toBeDisabled()
  })

  it("suppresses an immediate second install event after dismissal", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)
    await firePrompt("dismissed")
    await user.click(screen.getByRole("button", { name: "system:installPrompt.install" }))
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })

    await firePrompt()
    expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
  })

  it("suppresses an immediate second install event after prompt failure", async () => {
    const user = userEvent.setup()
    const rejectedPrompt = vi.fn(() => Promise.reject(new Error("prompt unavailable")))
    render(<InstallPrompt />)
    await firePrompt("accepted", rejectedPrompt)
    await user.click(screen.getByRole("button", { name: "system:installPrompt.install" }))
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })

    await firePrompt()
    expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
  })

  it("shows push education exactly at the dismissal boundary", () => {
    const baseTime = 10_000_000
    vi.spyOn(Date, "now").mockReturnValue(baseTime + DISMISS_TTL)
    window.localStorage.setItem(PUSH_DISMISS_KEY, String(baseTime))

    render(<InstallPrompt />)
    expect(screen.getByText("system:installPrompt.notificationsTitle")).toBeInTheDocument()
  })

  it("initializes push dismissal only once across preference changes", async () => {
    const future = Date.now() + DISMISS_TTL
    const originalGetItem = Storage.prototype.getItem
    let pushReads = 0
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
      this: Storage,
      key: string
    ) {
      if (key === PUSH_DISMISS_KEY) return pushReads++ === 0 ? String(future) : null
      return originalGetItem.call(this, key)
    })
    const { rerender } = render(<InstallPrompt />)
    expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()

    state.pushPrefs = createPushPrefs({ notificationPermission: "denied" })
    rerender(<InstallPrompt />)
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()
    })
  })

  it("uses the single-panel gap and the divider only when both panels are visible", async () => {
    render(<InstallPrompt />)
    const pushOnlyRoot = findPromptRoot()
    expect(findPanelContent(pushOnlyRoot)).toHaveClass("gap-4")
    expect(
      Array.from(pushOnlyRoot.querySelectorAll("div")).filter((el) =>
        String(el.className).includes("h-px")
      )
    ).toHaveLength(0)

    await firePrompt()
    const bothRoot = findPromptRoot()
    expect(findPanelContent(bothRoot)).toHaveClass("gap-6")
    expect(
      Array.from(bothRoot.querySelectorAll("div")).filter((el) =>
        String(el.className).includes("h-px")
      )
    ).toHaveLength(1)
  })

  it("renders a complete Safari guide link in the denied state", () => {
    state.pushPrefs = createPushPrefs({
      notificationPermission: "denied",
      safariIOS: true,
      safariGuideUrl: "https://example.com/guide",
    })
    render(<InstallPrompt />)

    const transCall = state.transCalls.at(-1)
    expect(transCall?.i18nKey).toBe("system:installPrompt.safariGuide")
    const link = transCall?.components?.link
    expect(link).toBeTruthy()
    if (link && typeof link === "object" && "props" in link) {
      expect(link.props).toMatchObject({
        href: "https://example.com/guide",
        target: "_blank",
        rel: "noreferrer noopener",
        className: "underline font-black",
      })
    }
  })

  it("applies disabled contracts for denied and default permission actions", async () => {
    state.pushPrefs = createPushPrefs({ notificationPermission: "denied", pushBusy: true })
    const denied = render(<InstallPrompt />)
    expect(screen.getByRole("button", { name: "system:installPrompt.check" })).toBeDisabled()
    denied.unmount()

    state.pushPrefs = createPushPrefs({ notificationPermission: "default", pushBusy: true })
    const busyDefault = render(<InstallPrompt />)
    expect(screen.getByRole("button", { name: "system:installPrompt.allow" })).toBeDisabled()
    busyDefault.unmount()

    state.pushPrefs = createPushPrefs({ notificationPermission: "default", pushInitializing: true })
    const initializingDefault = render(<InstallPrompt />)
    expect(screen.getByRole("button", { name: "system:installPrompt.allow" })).toBeDisabled()
    initializingDefault.unmount()

    state.pushPrefs = createPushPrefs({ notificationPermission: "default" })
    render(<InstallPrompt />)
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "system:installPrompt.allow" }))
    expect(state.pushPrefs.enableNotifications).toHaveBeenCalled()
  })

  it("applies enabled/disabled contracts to global and topic switches", () => {
    state.pushPrefs = createPushPrefs({
      notificationPermission: "transitioning" as NotificationPermission,
      notificationsEnabled: true,
      pushBusy: false,
      pushInitializing: false,
    })
    const enabled = render(<InstallPrompt />)
    expect(
      screen.getAllByRole("switch").every((control) => !control.hasAttribute("disabled"))
    ).toBe(true)
    enabled.unmount()

    state.pushPrefs = createPushPrefs({
      notificationPermission: "transitioning" as NotificationPermission,
      notificationsEnabled: false,
      topicKeys: ["schedule"],
      topicState: { schedule: true },
    })
    const notificationsDisabled = render(<InstallPrompt />)
    const disabledTopicSwitches = screen.getAllByRole("switch")
    expect(disabledTopicSwitches[0]).not.toHaveAttribute("disabled")
    expect(
      disabledTopicSwitches.slice(1).every((control) => control.hasAttribute("disabled"))
    ).toBe(true)
    notificationsDisabled.unmount()

    state.pushPrefs = createPushPrefs({
      notificationPermission: "transitioning" as NotificationPermission,
      notificationsEnabled: true,
      pushBusy: true,
      topicKeys: ["schedule"],
      topicState: { schedule: true },
    })
    const busy = render(<InstallPrompt />)
    expect(screen.getAllByRole("switch").every((control) => control.hasAttribute("disabled"))).toBe(
      true
    )
    busy.unmount()
  })

  it("passes status interpolation values for denied, default, and granted states", () => {
    const cases: Array<Partial<PushPrefs>> = [
      { notificationPermission: "denied", permissionText: "Blocked" },
      { notificationPermission: "default", permissionText: "Ask" },
      {
        notificationPermission: "transitioning" as NotificationPermission,
        notificationsEnabled: true,
        permissionText: "Allowed",
      },
    ]
    for (const overrides of cases) {
      state.translationCalls.length = 0
      state.pushPrefs = createPushPrefs(overrides)
      const view = render(<InstallPrompt />)
      const statusCalls = state.translationCalls.filter(({ key }) =>
        ["system:installPrompt.status", "system:installPrompt.browserPermission"].includes(key)
      )
      expect(statusCalls.length).toBeGreaterThan(0)
      expect(statusCalls).toContainEqual(
        expect.objectContaining({
          options: expect.objectContaining({ status: overrides.permissionText }),
        })
      )
      view.unmount()
    }
  })

  it("keeps feedback severity styles and icons distinct", async () => {
    render(<InstallPrompt />)
    const severities = [
      ["error", "bg-error-bg/(--opacity-dim)", "lucide-triangle-alert"],
      ["success", "bg-success-bg/(--opacity-dim)", "lucide-circle-check"],
      ["info", "bg-brand/(--opacity-subtle)", "lucide-circle-check"],
    ] as const

    for (const [severity, expectedClass, iconClass] of severities) {
      await act(async () => {
        state.onNotify?.({ text: `feedback-${severity}`, severity })
        await Promise.resolve()
      })
      const text = await screen.findByText(`feedback-${severity}`)
      const container = text.closest("div")
      expect(container).toHaveClass(...expectedClass.split(" "))
      expect(container?.querySelector("svg")).toHaveClass(iconClass)
      const closeButton = container?.querySelector("button")
      expect(closeButton).toBeInTheDocument()
      await userEvent.setup().click(closeButton as Element)
      await waitFor(() =>
        expect(screen.queryByText(`feedback-${severity}`)).not.toBeInTheDocument()
      )
    }
  })

  it("keeps an update toast open when no update callback is supplied", async () => {
    render(<InstallPrompt />)
    await act(async () => {
      window.dispatchEvent(new CustomEvent(PWA_REFRESH_EVENT, { detail: {} }))
      await Promise.resolve()
    })

    const user = userEvent.setup()
    await user.click(await screen.findByText("system:installPrompt.reload"))
    expect(screen.getByText("system:installPrompt.updateAvailable")).toBeInTheDocument()
  })

  it("exposes complete ARIA and keyboard contracts for all prompt actions", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)
    const pushClose = screen.getByRole("button", {
      name: "system:installPrompt.notificationsClose",
    })
    await user.click(pushClose)
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()
    })

    await firePrompt()
    const installClose = screen.getByRole("button", { name: "system:installPrompt.closeOffer" })
    expect(installClose).toHaveClass("p-1.5", "rounded-xl")
    await user.click(installClose)
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })
  })
})
