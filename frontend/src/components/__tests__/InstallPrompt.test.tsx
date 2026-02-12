import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { type ReactNode } from "react"
import InstallPrompt from "@/components/InstallPrompt"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

const DISMISS_TTL = 1000 * 60 * 60 * 24 * 7

const mockUsePushPreferences = vi.fn()

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: (...args: unknown[]) => mockUsePushPreferences(...args),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) =>
      opts?.appName ? `${key} ${opts.appName}` : key,
  }),
  Trans: ({ i18nKey }: { children?: ReactNode; i18nKey: string }) => <span>{i18nKey}</span>,
}))

const createPushPreferencesState = () => ({
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
})

interface MockBeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
}

const fireBeforeInstallPrompt = () => {
  const event = new Event("beforeinstallprompt") as MockBeforeInstallPromptEvent
  event.prompt = vi.fn().mockResolvedValue(undefined)
  event.userChoice = Promise.resolve({ outcome: "dismissed" })
  act(() => {
    window.dispatchEvent(event)
  })
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
  mockUsePushPreferences.mockReturnValue(createPushPreferencesState())
})

describe("InstallPrompt", () => {
  it("keeps the install CTA visible when push education is dismissed", async () => {
    render(<InstallPrompt />)
    fireBeforeInstallPrompt()

    await waitFor(() => {
      expect(
        screen.getByText("system:installPrompt.installTitle navigation:brandName")
      ).toBeInTheDocument()
      expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByLabelText("system:installPrompt.notificationsClose"))

    await waitFor(() => {
      expect(screen.queryByText("system:installPrompt.manageNotifications")).not.toBeInTheDocument()
    })

    expect(
      screen.getByText("system:installPrompt.installTitle navigation:brandName")
    ).toBeInTheDocument()
  })

  it("keeps push education active when the install CTA is dismissed", async () => {
    render(<InstallPrompt />)
    fireBeforeInstallPrompt()

    await waitFor(() => {
      expect(
        screen.getByText("system:installPrompt.installTitle navigation:brandName")
      ).toBeInTheDocument()
      expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByLabelText("system:installPrompt.closeOffer"))

    await waitFor(() => {
      expect(
        screen.queryByText("system:installPrompt.installTitle navigation:brandName")
      ).not.toBeInTheDocument()
    })

    expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
  })

  it("applies the push dismissal TTL independently of the install CTA", async () => {
    const nowSpy = vi.spyOn(Date, "now")
    const baseTime = DISMISS_TTL * 10
    let nowValue = baseTime
    nowSpy.mockImplementation(() => nowValue)

    try {
      const initial = render(<InstallPrompt />)
      fireBeforeInstallPrompt()

      await waitFor(() => {
        expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const closeButton = await screen.findByLabelText("system:installPrompt.notificationsClose")
      await user.click(closeButton)
      initial.unmount()

      nowValue = baseTime + DISMISS_TTL - 1000

      const suppressedRender = render(<InstallPrompt />)
      fireBeforeInstallPrompt()

      await waitFor(() => {
        expect(
          screen.getByText("system:installPrompt.installTitle navigation:brandName")
        ).toBeInTheDocument()
      })
      expect(screen.queryByText("system:installPrompt.manageNotifications")).not.toBeInTheDocument()
      suppressedRender.unmount()

      nowValue = baseTime + DISMISS_TTL + 1000
      const finalRender = render(<InstallPrompt />)

      await waitFor(() => {
        expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
      })

      finalRender.unmount()
    } finally {
      nowSpy.mockRestore()
    }
  })

  it("applies the install dismissal TTL independently of push education", async () => {
    const nowSpy = vi.spyOn(Date, "now")
    const baseTime = DISMISS_TTL * 10
    let nowValue = baseTime
    nowSpy.mockImplementation(() => nowValue)

    try {
      const initial = render(<InstallPrompt />)
      fireBeforeInstallPrompt()

      await waitFor(() => {
        expect(
          screen.getByText("system:installPrompt.installTitle navigation:brandName")
        ).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.click(screen.getByLabelText("system:installPrompt.closeOffer"))
      initial.unmount()

      nowValue = baseTime + DISMISS_TTL - 1000

      const suppressedRender = render(<InstallPrompt />)
      fireBeforeInstallPrompt()

      await waitFor(() => {
        expect(screen.getByText("system:installPrompt.manageNotifications")).toBeInTheDocument()
      })
      expect(
        screen.queryByText("system:installPrompt.installTitle navigation:brandName")
      ).not.toBeInTheDocument()
      suppressedRender.unmount()

      nowValue = baseTime + DISMISS_TTL + 1000
      const finalRender = render(<InstallPrompt />)
      fireBeforeInstallPrompt()

      await waitFor(() => {
        expect(
          screen.getByText("system:installPrompt.installTitle navigation:brandName")
        ).toBeInTheDocument()
      })

      finalRender.unmount()
    } finally {
      nowSpy.mockRestore()
    }
  })
})
