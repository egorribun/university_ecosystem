import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
  Trans: ({ i18nKey }: { i18nKey: string }) => i18nKey,
}))

// Mutable hook return — each test tweaks the relevant fields before render.
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

const enableNotifications = vi.fn(() => Promise.resolve())
const disableNotifications = vi.fn(() => Promise.resolve())
const topicToggleInner = vi.fn()
const handleTopicToggle = vi.fn((..._a: unknown[]) => topicToggleInner)

let pushPrefs: PushPrefs

function resetPushPrefs(overrides: Partial<PushPrefs> = {}) {
  pushPrefs = {
    topicKeys: ["schedule", "news", "events", "system"],
    topicState: { schedule: true, news: true, events: false, system: true },
    pushSupported: true,
    notificationPermission: "default",
    notificationsEnabled: false,
    pushBusy: false,
    pushInitializing: false,
    permissionText: "Allowed",
    enableNotifications,
    disableNotifications,
    handleTopicToggle,
    safariIOS: false,
    safariGuideUrl: "https://support.apple.com/guide",
    ...overrides,
  }
}

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: (options?: { onNotify?: (toast: unknown) => void }) => {
    // capture onNotify so a test can drive the feedback toast branch
    onNotifyRef = options?.onNotify ?? null
    return pushPrefs
  },
}))

let onNotifyRef: ((toast: unknown) => void) | null = null

import InstallPrompt from "@/components/pwa/InstallPrompt"
import { PWA_REFRESH_EVENT } from "@/app/pwaEvents"

type UserChoiceOutcome = "accepted" | "dismissed"

/** Build a fake beforeinstallprompt event with a controllable userChoice. */
function makeBeforeInstallPromptEvent(outcome: UserChoiceOutcome = "accepted") {
  const event = new Event("beforeinstallprompt") as Event & {
    prompt: () => Promise<void>
    userChoice: Promise<{ outcome: UserChoiceOutcome }>
    preventDefault: () => void
  }
  ;(event as { prompt: () => Promise<void> }).prompt = vi.fn(() => Promise.resolve())
  ;(event as { userChoice: Promise<{ outcome: UserChoiceOutcome }> }).userChoice = Promise.resolve({
    outcome,
  })
  return event
}

/** Fire the beforeinstallprompt event so the install panel becomes eligible. */
async function fireBeforeInstallPrompt(outcome: UserChoiceOutcome = "accepted") {
  const event = makeBeforeInstallPromptEvent(outcome)
  await act(async () => {
    window.dispatchEvent(event)
    await Promise.resolve()
  })
  return event
}

describe("InstallPrompt", () => {
  beforeEach(() => {
    resetPushPrefs()
    enableNotifications.mockClear()
    disableNotifications.mockClear()
    handleTopicToggle.mockClear()
    topicToggleInner.mockClear()
    onNotifyRef = null
    window.localStorage.clear()
    vi.stubEnv("VITE_LHCI", "")
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    window.localStorage.clear()
  })

  it("renders the push-education panel by default (permission=default)", () => {
    render(<InstallPrompt />)
    expect(screen.getByText("system:installPrompt.notificationsTitle")).toBeInTheDocument()
    expect(
      screen.getByText("system:installPrompt.defaultPermissionDescription")
    ).toBeInTheDocument()
    // No install panel until a beforeinstallprompt event arrives.
    expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
  })

  it("shows the install panel after a beforeinstallprompt event", async () => {
    render(<InstallPrompt />)
    await fireBeforeInstallPrompt()
    expect(screen.getByText("system:installPrompt.installTitle")).toBeInTheDocument()
    expect(screen.getByText("system:installPrompt.description")).toBeInTheDocument()
    expect(screen.getByText("system:installPrompt.install")).toBeInTheDocument()
  })

  it("calls prompt() and hides the panel when the user accepts the install", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)
    const event = await fireBeforeInstallPrompt("accepted")

    await user.click(screen.getByText("system:installPrompt.install"))

    await waitFor(() => {
      expect((event as unknown as { prompt: ReturnType<typeof vi.fn> }).prompt).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })
  })

  it("hides the panel after a dismissed install prompt and remembers the choice", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)
    const event = await fireBeforeInstallPrompt("dismissed")

    await user.click(screen.getByText("system:installPrompt.install"))

    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })
    expect((event as unknown as { prompt: ReturnType<typeof vi.fn> }).prompt).toHaveBeenCalled()
    expect(window.localStorage.getItem("ecosystem.pwa.install.dismissedAt")).not.toBeNull()
  })

  it("fails safe when the install prompt rejects", async () => {
    const user = userEvent.setup()
    const event = makeBeforeInstallPromptEvent()
    event.prompt = vi.fn(() => Promise.reject(new Error("prompt failed")))
    render(<InstallPrompt />)

    await act(async () => {
      window.dispatchEvent(event)
      await Promise.resolve()
    })
    await user.click(screen.getByText("system:installPrompt.install"))

    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })
    expect(window.localStorage.getItem("ecosystem.pwa.install.dismissedAt")).not.toBeNull()
  })

  it("ignores malformed and currently suppressed install timestamps", async () => {
    window.localStorage.setItem("ecosystem.pwa.install.dismissedAt", "not-a-timestamp")
    const first = render(<InstallPrompt />)
    await fireBeforeInstallPrompt()
    expect(screen.getByText("system:installPrompt.installTitle")).toBeInTheDocument()
    first.unmount()

    window.localStorage.setItem(
      "ecosystem.pwa.install.dismissedAt",
      String(Date.now() + 7 * 24 * 60 * 60 * 1000)
    )
    render(<InstallPrompt />)
    await fireBeforeInstallPrompt()
    expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
  })

  it("continues when localStorage read, write, and remove operations fail", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("read failed")
    })
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("write failed")
    })
    const removeItem = vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("remove failed")
    })
    const user = userEvent.setup()

    const first = render(<InstallPrompt />)
    await fireBeforeInstallPrompt("dismissed")
    await user.click(screen.getByText("system:installPrompt.install"))
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })
    first.unmount()

    render(<InstallPrompt />)
    await fireBeforeInstallPrompt("accepted")
    await user.click(screen.getByText("system:installPrompt.install"))
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })

    expect(getItem).toHaveBeenCalled()
    expect(setItem).toHaveBeenCalled()
    expect(removeItem).toHaveBeenCalled()
    getItem.mockRestore()
    setItem.mockRestore()
    removeItem.mockRestore()
  })

  it("remembers a dismissal and hides the install panel when the user clicks Later", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)
    await fireBeforeInstallPrompt()

    await user.click(screen.getByText("system:installPrompt.later"))

    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })
    expect(window.localStorage.getItem("ecosystem.pwa.install.dismissedAt")).not.toBeNull()
  })

  it("dismisses the install panel via the close (X) button", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)
    await fireBeforeInstallPrompt()

    await user.click(screen.getByRole("button", { name: "system:installPrompt.closeOffer" }))

    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.installTitle")).not.toBeInTheDocument()
    })
  })

  it("dismisses the push panel via its close button and persists the dismissal", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)

    await user.click(
      screen.getByRole("button", { name: "system:installPrompt.notificationsClose" })
    )

    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()
    })
    expect(window.localStorage.getItem("ecosystem.push.education.dismissedAt")).not.toBeNull()
  })

  it("renders the unsupported branch when push is not supported", () => {
    resetPushPrefs({ pushSupported: false })
    render(<InstallPrompt />)
    expect(screen.getByText("system:installPrompt.unsupported")).toBeInTheDocument()
  })

  it("renders the denied branch with a check button", async () => {
    resetPushPrefs({ notificationPermission: "denied" })
    const user = userEvent.setup()
    render(<InstallPrompt />)

    expect(screen.getByText("system:installPrompt.blocked")).toBeInTheDocument()
    expect(screen.getByText("system:installPrompt.check")).toBeInTheDocument()

    await user.click(screen.getByText("system:installPrompt.check"))
    expect(enableNotifications).toHaveBeenCalled()
  })

  it("shows the Safari iOS guide inside the denied branch when safariIOS is true", () => {
    resetPushPrefs({ notificationPermission: "denied", safariIOS: true })
    render(<InstallPrompt />)
    // <Trans> mock renders the i18nKey verbatim.
    expect(screen.getByText("system:installPrompt.safariGuide")).toBeInTheDocument()
  })

  it("calls enableNotifications from the default-permission Allow button", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)

    await user.click(screen.getByText("system:installPrompt.allow"))
    expect(enableNotifications).toHaveBeenCalled()
  })

  it("hides the push panel when permission is already granted (effect granted-branch)", () => {
    // When pushSupported && permission === "granted", the visibility effect
    // sets pushVisible=false on mount — the education panel is suppressed
    // because there's nothing left to ask the user for.
    resetPushPrefs({ notificationPermission: "granted", notificationsEnabled: true })
    render(<InstallPrompt />)

    expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()
    expect(screen.queryByText("system:installPrompt.toggleLabel")).not.toBeInTheDocument()
  })

  it("hides the push panel entirely under the VITE_LHCI gate", () => {
    vi.stubEnv("VITE_LHCI", "true")
    render(<InstallPrompt />)
    expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()
  })

  it("renders the service-worker update toast on PWA_REFRESH_EVENT and reloads on click", async () => {
    const user = userEvent.setup()
    const update = vi.fn(() => Promise.resolve())
    render(<InstallPrompt />)

    await act(async () => {
      window.dispatchEvent(new CustomEvent(PWA_REFRESH_EVENT, { detail: { update } }))
      await Promise.resolve()
    })

    expect(screen.getByText("system:installPrompt.updateAvailable")).toBeInTheDocument()

    await user.click(screen.getByText("system:installPrompt.reload"))
    expect(update).toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.updateAvailable")).not.toBeInTheDocument()
    })
  })

  it("dismisses the update toast via its close button without reloading", async () => {
    const user = userEvent.setup()
    const update = vi.fn(() => Promise.resolve())
    render(<InstallPrompt />)

    await act(async () => {
      window.dispatchEvent(new CustomEvent(PWA_REFRESH_EVENT, { detail: { update } }))
      await Promise.resolve()
    })

    const toast = screen.getByText("system:installPrompt.updateAvailable").closest("div")
    expect(toast).not.toBeNull()
    const closeButton = toast!.parentElement!.querySelector("button:last-of-type")
    await user.click(closeButton as Element)

    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.updateAvailable")).not.toBeInTheDocument()
    })
    expect(update).not.toHaveBeenCalled()
  })

  it("renders a feedback toast (success) when the hook's onNotify fires, and closes it", async () => {
    const user = userEvent.setup()
    render(<InstallPrompt />)
    expect(onNotifyRef).toBeTypeOf("function")

    await act(async () => {
      onNotifyRef?.({ text: "Subscribed!", severity: "success" })
      await Promise.resolve()
    })

    const feedback = await screen.findByText("Subscribed!")
    expect(feedback).toBeInTheDocument()

    // Close the feedback toast (the trailing X button within its container).
    const container = feedback.closest("div")
    const closeButton = container!.querySelector("button")
    await user.click(closeButton as Element)

    await waitFor(() => {
      expect(screen.queryByText("Subscribed!")).not.toBeInTheDocument()
    })
  })

  it("renders an error-severity feedback toast", async () => {
    render(<InstallPrompt />)

    await act(async () => {
      onNotifyRef?.({ text: "Something broke", severity: "error" })
      await Promise.resolve()
    })

    expect(await screen.findByText("Something broke")).toBeInTheDocument()
  })

  it("renders an informational feedback toast", async () => {
    render(<InstallPrompt />)

    await act(async () => {
      onNotifyRef?.({ text: "Heads up", severity: "info" })
      await Promise.resolve()
    })

    expect(await screen.findByText("Heads up")).toBeInTheDocument()
  })

  it("renders both install and push panels (divider branch) when both are eligible", async () => {
    render(<InstallPrompt />)
    await fireBeforeInstallPrompt()

    expect(screen.getByText("system:installPrompt.installTitle")).toBeInTheDocument()
    expect(screen.getByText("system:installPrompt.notificationsTitle")).toBeInTheDocument()
  })
})
