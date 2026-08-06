import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { type ReactNode } from "react"
import { renderToString } from "react-dom/server"
import InstallPrompt, { togglePushNotifications } from "@/components/pwa/InstallPrompt"
import { PWA_REFRESH_EVENT } from "@/app/pwaEvents"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

const mockUsePushPreferences = vi.fn()

const lastNotify = { fn: null as ((toast: unknown) => void) | null }

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: (opts: { onNotify?: (toast: unknown) => void }) => {
    lastNotify.fn = opts?.onNotify ?? null
    return mockUsePushPreferences(opts)
  },
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) =>
      opts?.appName ? `${key} ${opts.appName}` : key,
  }),
  Trans: ({ i18nKey }: { children?: ReactNode; i18nKey: string }) => <span>{i18nKey}</span>,
}))

const createPushPreferencesState = (overrides: Record<string, unknown> = {}) => ({
  topicKeys: [],
  topicState: {},
  pushSupported: true,
  notificationPermission: "default" as NotificationPermission,
  notificationsEnabled: false,
  pushBusy: false,
  pushInitializing: false,
  permissionText: "default",
  selectedTopicsDescription: "",
  enableNotifications: vi.fn(),
  disableNotifications: vi.fn(),
  handleTopicToggle: () => () => undefined,
  safariIOS: false,
  safariGuideUrl: "",
  ...overrides,
})

interface MockBeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
}

const fireBeforeInstallPrompt = (outcome: "accepted" | "dismissed" = "dismissed") => {
  const event = new Event("beforeinstallprompt") as MockBeforeInstallPromptEvent
  event.prompt = vi.fn().mockResolvedValue(undefined)
  event.userChoice = Promise.resolve({ outcome })
  act(() => {
    window.dispatchEvent(event)
  })
  return event
}

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

beforeEach(() => {
  localStorage.clear()
  lastNotify.fn = null
  mockUsePushPreferences.mockReturnValue(createPushPreferencesState())
})

describe("InstallPrompt — branches", () => {
  it("clears the install suppress when the app is installed", async () => {
    render(<InstallPrompt />)
    fireBeforeInstallPrompt()

    await waitFor(() => {
      expect(
        screen.getByText("system:installPrompt.installTitle navigation:brandName")
      ).toBeInTheDocument()
    })

    act(() => {
      window.dispatchEvent(new Event("appinstalled"))
    })

    await waitFor(() => {
      expect(
        screen.queryByText("system:installPrompt.installTitle navigation:brandName")
      ).not.toBeInTheDocument()
    })
  })

  it("renders the unsupported warning when push is not supported", async () => {
    mockUsePushPreferences.mockReturnValue(createPushPreferencesState({ pushSupported: false }))
    render(<InstallPrompt />)

    await waitFor(() => {
      expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
    })
    expect(screen.getByText("system:installPrompt.unsupported")).toBeInTheDocument()
  })

  it("ignores malformed dismissal timestamps", async () => {
    localStorage.setItem("ecosystem.pwa.install.dismissedAt", "not-a-number")

    render(<InstallPrompt />)

    await waitFor(() => {
      expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
    })
  })

  it("renders the granted notification topic controls during permission transition", async () => {
    const enableNotifications = vi.fn()
    const disableNotifications = vi.fn()
    const topicToggle = vi.fn()
    const handleTopicToggle = vi.fn(() => topicToggle)
    mockUsePushPreferences.mockReturnValue(
      createPushPreferencesState({
        notificationPermission: "default",
        notificationsEnabled: false,
        topicKeys: ["events"],
        topicState: { events: false },
        enableNotifications,
        disableNotifications,
        handleTopicToggle,
      })
    )

    const { rerender } = render(<InstallPrompt />)

    await waitFor(() => {
      expect(screen.getByText("system:installPrompt.allow")).toBeInTheDocument()
    })

    mockUsePushPreferences.mockReturnValue(
      createPushPreferencesState({
        notificationPermission: "granted",
        notificationsEnabled: true,
        topicKeys: ["events"],
        topicState: { events: true },
        enableNotifications,
        disableNotifications,
        handleTopicToggle,
      })
    )
    rerender(<InstallPrompt />)

    expect(screen.queryByText("system:installPrompt.toggleLabel")).not.toBeInTheDocument()
    togglePushNotifications(false, enableNotifications, disableNotifications)
    togglePushNotifications(true, enableNotifications, disableNotifications)
    expect(enableNotifications).toHaveBeenCalledOnce()
    expect(disableNotifications).toHaveBeenCalledOnce()
    expect(topicToggle).not.toHaveBeenCalled()
  })

  it("renders the blocked state when permission is denied", async () => {
    mockUsePushPreferences.mockReturnValue(
      createPushPreferencesState({ notificationPermission: "denied" })
    )
    render(<InstallPrompt />)

    await waitFor(() => {
      expect(
        screen.getByText("system:installPrompt.blocked navigation:brandName")
      ).toBeInTheDocument()
    })
    expect(screen.getByText("system:installPrompt.check")).toBeInTheDocument()
  })

  it("shows the Safari iOS guide in the denied state", async () => {
    mockUsePushPreferences.mockReturnValue(
      createPushPreferencesState({
        notificationPermission: "denied",
        safariIOS: true,
        safariGuideUrl: "https://example.com/guide",
      })
    )
    render(<InstallPrompt />)

    await waitFor(() => {
      expect(screen.getByText("system:installPrompt.safariGuide")).toBeInTheDocument()
    })
  })

  it("shows an informational feedback toast with the neutral style", async () => {
    render(<InstallPrompt />)

    await waitFor(() => {
      expect(lastNotify.fn).toBeTypeOf("function")
    })

    act(() => {
      lastNotify.fn?.({ text: "info", severity: "info" })
    })

    expect(await screen.findByText("info")).toBeInTheDocument()
  })

  it("invokes enableNotifications from the denied state check button", async () => {
    const enableNotifications = vi.fn()
    mockUsePushPreferences.mockReturnValue(
      createPushPreferencesState({ notificationPermission: "denied", enableNotifications })
    )
    render(<InstallPrompt />)

    const user = userEvent.setup()
    const checkButton = await screen.findByText("system:installPrompt.check")
    await user.click(checkButton)

    expect(enableNotifications).toHaveBeenCalledTimes(1)
  })

  it("invokes enableNotifications from the default-permission allow button", async () => {
    const enableNotifications = vi.fn()
    mockUsePushPreferences.mockReturnValue(
      createPushPreferencesState({ notificationPermission: "default", enableNotifications })
    )
    render(<InstallPrompt />)

    const user = userEvent.setup()
    const allowButton = await screen.findByText("system:installPrompt.allow")
    await user.click(allowButton)

    expect(enableNotifications).toHaveBeenCalledTimes(1)
  })

  it("completes an accepted install and clears its deferred prompt", async () => {
    render(<InstallPrompt />)
    const event = fireBeforeInstallPrompt("accepted")

    await waitFor(() => {
      expect(
        screen.getByText("system:installPrompt.installTitle navigation:brandName")
      ).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "system:installPrompt.install" }))

    await waitFor(() => {
      expect(event.prompt).toHaveBeenCalledOnce()
      expect(
        screen.queryByText("system:installPrompt.installTitle navigation:brandName")
      ).not.toBeInTheDocument()
    })
    expect(localStorage.getItem("ecosystem.pwa.install.dismissedAt")).toBeNull()
  })

  it("suppresses a dismissed install and records the dismissal timestamp", async () => {
    render(<InstallPrompt />)
    const event = fireBeforeInstallPrompt("dismissed")

    await waitFor(() => {
      expect(
        screen.getByText("system:installPrompt.installTitle navigation:brandName")
      ).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "system:installPrompt.install" }))

    await waitFor(() => {
      expect(event.prompt).toHaveBeenCalledOnce()
      expect(
        screen.queryByText("system:installPrompt.installTitle navigation:brandName")
      ).not.toBeInTheDocument()
    })
    expect(localStorage.getItem("ecosystem.pwa.install.dismissedAt")).not.toBeNull()
  })

  it("suppresses the install prompt when the browser prompt rejects", async () => {
    render(<InstallPrompt />)
    const event = fireBeforeInstallPrompt("dismissed")
    event.prompt = vi.fn().mockRejectedValue(new Error("prompt unavailable"))

    await waitFor(() => {
      expect(
        screen.getByText("system:installPrompt.installTitle navigation:brandName")
      ).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "system:installPrompt.install" }))

    await waitFor(() => {
      expect(
        screen.queryByText("system:installPrompt.installTitle navigation:brandName")
      ).not.toBeInTheDocument()
    })
    expect(localStorage.getItem("ecosystem.pwa.install.dismissedAt")).not.toBeNull()
  })

  it("surfaces a feedback toast via the onNotify callback", async () => {
    render(<InstallPrompt />)

    await waitFor(() => {
      expect(lastNotify.fn).toBeTypeOf("function")
    })

    act(() => {
      lastNotify.fn?.({ text: "saved", severity: "success" })
    })

    await waitFor(() => {
      expect(screen.getByText("saved")).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByText("saved").closest("div")!.querySelector("button")!)

    await waitFor(() => {
      expect(screen.queryByText("saved")).not.toBeInTheDocument()
    })
  })

  it("renders an error-severity feedback toast", async () => {
    render(<InstallPrompt />)

    await waitFor(() => {
      expect(lastNotify.fn).toBeTypeOf("function")
    })

    act(() => {
      lastNotify.fn?.({ text: "boom", severity: "error" })
    })

    await waitFor(() => {
      expect(screen.getByText("boom")).toBeInTheDocument()
    })
  })

  it("runs the SW update toast lifecycle and triggers reload", async () => {
    const update = vi.fn().mockResolvedValue(undefined)
    render(<InstallPrompt />)

    act(() => {
      window.dispatchEvent(new CustomEvent(PWA_REFRESH_EVENT, { detail: { update } }))
    })

    await waitFor(() => {
      expect(screen.getByText("system:installPrompt.updateAvailable")).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByText("system:installPrompt.reload"))

    expect(update).toHaveBeenCalledTimes(1)
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.updateAvailable")).not.toBeInTheDocument()
    })
  })

  it("closes the SW update toast without reloading", async () => {
    const update = vi.fn().mockResolvedValue(undefined)
    render(<InstallPrompt />)

    act(() => {
      window.dispatchEvent(new CustomEvent(PWA_REFRESH_EVENT, { detail: { update } }))
    })

    const toast = await screen.findByText("system:installPrompt.updateAvailable")
    const closeButton = toast
      .closest("div")!
      .parentElement!.querySelector("button:last-of-type") as HTMLButtonElement

    const user = userEvent.setup()
    await user.click(closeButton)

    expect(update).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.updateAvailable")).not.toBeInTheDocument()
    })
  })

  it("ignores an update-toast reload event without an update callback", async () => {
    render(<InstallPrompt />)

    act(() => {
      window.dispatchEvent(new CustomEvent(PWA_REFRESH_EVENT, { detail: {} }))
    })

    const user = userEvent.setup()
    await user.click(await screen.findByText("system:installPrompt.reload"))
    expect(screen.getByText("system:installPrompt.updateAvailable")).toBeInTheDocument()
  })

  it("fails closed when localStorage read, write, or remove operations throw", async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage read blocked")
    })
    try {
      render(<InstallPrompt />)
      await waitFor(() => {
        expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
      })
    } finally {
      getItemSpy.mockRestore()
    }

    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage write blocked")
    })
    try {
      const event = fireBeforeInstallPrompt("dismissed")
      await waitFor(() => {
        expect(
          screen.getByText("system:installPrompt.installTitle navigation:brandName")
        ).toBeInTheDocument()
      })
      const user = userEvent.setup()
      await user.click(screen.getByRole("button", { name: "system:installPrompt.closeOffer" }))
      expect(event.prompt).not.toHaveBeenCalled()
    } finally {
      setItemSpy.mockRestore()
    }

    const removeItemSpy = vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("storage remove blocked")
    })
    try {
      act(() => window.dispatchEvent(new Event("appinstalled")))
    } finally {
      removeItemSpy.mockRestore()
    }
  })

  it("skips install lifecycle listeners when the app is already standalone", () => {
    const previousMatchMedia = window.matchMedia
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })

    const { unmount } = render(<InstallPrompt />)
    act(() => window.dispatchEvent(new Event("beforeinstallprompt")))
    expect(
      screen.queryByText("system:installPrompt.installTitle navigation:brandName")
    ).not.toBeInTheDocument()

    unmount()
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: previousMatchMedia,
    })
  })

  it("uses the safe non-browser eligibility fallback during SSR", () => {
    const browserWindow = window
    vi.stubGlobal("window", undefined)
    try {
      expect(renderToString(<InstallPrompt />)).toBe("")
    } finally {
      vi.stubGlobal("window", browserWindow)
    }
  })
})
