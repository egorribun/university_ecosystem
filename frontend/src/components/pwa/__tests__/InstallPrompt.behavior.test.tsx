import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import InstallPrompt from "@/components/pwa/InstallPrompt"
import {
  consumePendingPushEducation,
  PWA_REFRESH_EVENT,
  requestPushEducation,
} from "@/app/pwaEvents"
import type { NotificationToast, UsePushPreferencesOptions } from "@/hooks/usePushPreferences"
import enCommon from "@/i18n/locales/en/common.json"
import enNavigation from "@/i18n/locales/en/navigation.json"
import enNotifications from "@/i18n/locales/en/notifications.json"
import enSystem from "@/i18n/locales/en/system.json"
import ruCommon from "@/i18n/locales/ru/common.json"
import ruNavigation from "@/i18n/locales/ru/navigation.json"
import ruNotifications from "@/i18n/locales/ru/notifications.json"
import ruSystem from "@/i18n/locales/ru/system.json"
import { useAuthStore } from "@/stores/useAuthStore"
import type { User } from "@/types/User"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

const push = vi.hoisted(() => ({
  supported: true,
  permission: "default" as NotificationPermission,
  busy: false,
  initializing: false,
  permissionText: "",
  enable: vi.fn<() => Promise<void>>(),
  notify: undefined as UsePushPreferencesOptions["onNotify"],
}))

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: (options: UsePushPreferencesOptions) => {
    push.notify = options.onNotify
    return {
      pushSupported: push.supported,
      notificationPermission: push.permission,
      pushBusy: push.busy,
      pushInitializing: push.initializing,
      permissionText: push.permissionText,
      enableNotifications: push.enable,
    }
  },
}))

const user: User = { id: "1", email: "student@example.test", is_active: true }
const INSTALL_DISMISS_KEY = "ecosystem.pwa.install.dismissedAt"
const DISMISS_TTL = 7 * 24 * 60 * 60 * 1000
const NOW = Date.UTC(2026, 9, 3, 12)
const originalViewport = Object.getOwnPropertyDescriptor(window, "visualViewport")
const originalClientWidth = Object.getOwnPropertyDescriptor(document.documentElement, "clientWidth")
let previousAuth: Pick<ReturnType<typeof useAuthStore.getState>, "user" | "loading">
let previousHistory: { url: string; state: unknown }

async function renderPrompt(language: "en" | "ru" = "en") {
  const i18n = createInstance()
  await i18n.init({
    lng: language,
    fallbackLng: false,
    resources: {
      en: {
        common: enCommon,
        navigation: enNavigation,
        notifications: enNotifications,
        system: enSystem,
      },
      ru: {
        common: ruCommon,
        navigation: ruNavigation,
        notifications: ruNotifications,
        system: ruSystem,
      },
    },
  })
  push.permissionText = i18n.t("notifications:permission.default")
  const element = () => (
    <I18nextProvider i18n={i18n}>
      <InstallPrompt />
    </I18nextProvider>
  )
  const view = render(element())
  return { ...view, refresh: () => view.rerender(element()) }
}

function offerInstall(
  outcome: "accepted" | "dismissed" = "accepted",
  userChoice = Promise.resolve({ outcome })
) {
  const event = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), {
    prompt: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
    userChoice,
  })
  act(() => window.dispatchEvent(event))
  return event
}

const requestEducation = () => act(() => requestPushEducation(user.id))

beforeEach(() => {
  const { user: previousUser, loading } = useAuthStore.getState()
  previousAuth = { user: previousUser, loading }
  previousHistory = { url: window.location.href, state: window.history.state }
  consumePendingPushEducation(user.id)
  localStorage.clear()
  useAuthStore.setState({ user, loading: false })
  window.history.replaceState(null, "", "/events")
  vi.stubEnv("VITE_LHCI", "")
  vi.spyOn(Date, "now").mockReturnValue(NOW)
  push.supported = true
  push.permission = "default"
  push.busy = false
  push.initializing = false
  push.notify = undefined
  push.enable.mockReset().mockResolvedValue(undefined)
})

afterEach(() => {
  cleanup()
  useAuthStore.setState(previousAuth)
  window.history.replaceState(previousHistory.state, "", previousHistory.url)
  consumePendingPushEducation(user.id)
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
  localStorage.clear()
  if (originalViewport) Object.defineProperty(window, "visualViewport", originalViewport)
  else Reflect.deleteProperty(window, "visualViewport")
  if (originalClientWidth) {
    Object.defineProperty(document.documentElement, "clientWidth", originalClientWidth)
  } else Reflect.deleteProperty(document.documentElement, "clientWidth")
})

describe("InstallPrompt user behavior", () => {
  it.each([
    {
      language: "en" as const,
      title: "Install “GUU Ecosystem”",
      notifications: "Notifications",
      description: "Allow notifications to receive schedule updates, events, and important news.",
      status: "Status: not requested.",
      allow: "Allow",
      installClose: "Dismiss offer",
      pushClose: "Hide notifications guide",
    },
    {
      language: "ru" as const,
      title: "Установить «Экосистема ГУУ»",
      notifications: "Уведомления",
      description:
        "Разрешите уведомления, чтобы получать расписание, мероприятия и важные новости.",
      status: "Состояние: не запрошено.",
      allow: "Разрешить",
      installClose: "Скрыть предложение",
      pushClose: "Скрыть подсказки об уведомлениях",
    },
  ])("shows translated content and independent keyboard actions in $language", async (copy) => {
    const keyboard = userEvent.setup()
    await renderPrompt(copy.language)
    requestEducation()
    const install = offerInstall()

    expect(screen.getByRole("heading", { name: copy.title })).toBeVisible()
    expect(screen.getByRole("heading", { name: copy.notifications })).toBeVisible()
    expect(screen.getByText(copy.description)).toBeVisible()
    expect(screen.getByText(copy.status)).toBeVisible()
    expect(push.enable).not.toHaveBeenCalled()
    expect(install.prompt).not.toHaveBeenCalled()

    screen.getByRole("button", { name: copy.allow }).focus()
    await keyboard.keyboard("{Enter}")
    expect(push.enable).toHaveBeenCalledExactlyOnceWith()

    screen.getByRole("button", { name: copy.installClose }).focus()
    await keyboard.keyboard("{Enter}")
    expect(screen.queryByRole("heading", { name: copy.title })).not.toBeInTheDocument()
    expect(screen.getByRole("heading", { name: copy.notifications })).toBeVisible()

    screen.getByRole("button", { name: copy.pushClose }).focus()
    await keyboard.keyboard("{Enter}")
    expect(screen.queryByRole("heading", { name: copy.notifications })).not.toBeInTheDocument()
    expect(install.prompt).not.toHaveBeenCalled()
  })

  it.each([
    { language: "en" as const, close: "Close", update: "Update available", reload: "Reload" },
    {
      language: "ru" as const,
      close: "Закрыть",
      update: "Доступно обновление",
      reload: "Перезагрузить",
    },
  ])(
    "names each toast close action in $language and keeps their lifecycles independent",
    async (copy) => {
      await renderPrompt(copy.language)
      const feedback: NotificationToast = { text: "Subscription saved", severity: "success" }
      const firstUpdate = vi.fn<() => Promise<void>>().mockResolvedValue(undefined)
      act(() => {
        push.notify?.(feedback)
        window.dispatchEvent(
          new CustomEvent(PWA_REFRESH_EVENT, { detail: { update: firstUpdate } })
        )
      })

      const feedbackContainer = screen.getByText(feedback.text).parentElement!
      fireEvent.click(within(feedbackContainer).getByRole("button", { name: copy.close }))
      expect(screen.queryByText(feedback.text)).not.toBeInTheDocument()
      expect(screen.getByText(copy.update)).toBeVisible()
      fireEvent.click(screen.getByRole("button", { name: copy.close }))
      expect(screen.queryByText(copy.update)).not.toBeInTheDocument()
      expect(firstUpdate).not.toHaveBeenCalled()

      const nextUpdate = vi.fn<() => Promise<void>>().mockResolvedValue(undefined)
      act(() =>
        window.dispatchEvent(new CustomEvent(PWA_REFRESH_EVENT, { detail: { update: nextUpdate } }))
      )
      fireEvent.click(screen.getByRole("button", { name: copy.reload }))
      expect(nextUpdate).toHaveBeenCalledExactlyOnceWith()
      expect(firstUpdate).not.toHaveBeenCalled()
      expect(screen.queryByText(copy.update)).not.toBeInTheDocument()
    }
  )

  it("defers the browser's cancellable install event until the user chooses Install", async () => {
    await renderPrompt()
    const event = offerInstall()
    expect(event.defaultPrevented).toBe(true)
    expect(event.prompt).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Install" }))
    await waitFor(() => expect(screen.queryByRole("heading")).not.toBeInTheDocument())
    expect(event.prompt).toHaveBeenCalledExactlyOnceWith()
  })

  it.each(["Later", "Dismiss offer", "dismissed", "prompt rejection"] as const)(
    "suppresses a repeated install event for seven days after %s without relying on storage",
    async (dismissal) => {
      await renderPrompt()
      const first = offerInstall("dismissed")
      if (dismissal === "prompt rejection") first.prompt.mockRejectedValue(new Error("unavailable"))
      const button =
        dismissal === "dismissed" || dismissal === "prompt rejection" ? "Install" : dismissal
      fireEvent.click(screen.getByRole("button", { name: button }))
      await waitFor(() => expect(screen.queryByRole("heading")).not.toBeInTheDocument())
      expect(localStorage.getItem(INSTALL_DISMISS_KEY)).toBe(String(NOW))
      localStorage.removeItem(INSTALL_DISMISS_KEY)

      vi.mocked(Date.now).mockReturnValue(NOW + DISMISS_TTL - 1)
      const suppressed = offerInstall()
      expect(screen.queryByRole("heading")).not.toBeInTheDocument()
      expect(suppressed.prompt).not.toHaveBeenCalled()

      vi.mocked(Date.now).mockReturnValue(NOW + DISMISS_TTL)
      const available = offerInstall()
      expect(available.defaultPrevented).toBe(true)
      expect(screen.getByRole("button", { name: "Install" })).toBeEnabled()
    }
  )

  it("prevents repeat install actions while the browser's user choice is pending", async () => {
    const keyboard = userEvent.setup()
    await renderPrompt()
    let choose!: (choice: { outcome: "accepted" | "dismissed" }) => void
    const userChoice = new Promise<{ outcome: "accepted" | "dismissed" }>((resolve) => {
      choose = resolve
    })
    const event = offerInstall("accepted", userChoice)
    const install = screen.getByRole("button", { name: "Install" })
    try {
      await keyboard.click(install)
      expect(install).toBeDisabled()
      expect(install).toHaveAttribute("aria-busy", "true")
      await keyboard.click(install)
      expect(event.prompt).toHaveBeenCalledOnce()

      await act(async () => choose({ outcome: "accepted" }))
      expect(screen.queryByRole("heading")).not.toBeInTheDocument()
      expect(localStorage.getItem(INSTALL_DISMISS_KEY)).toBeNull()
    } finally {
      await act(async () => {
        choose({ outcome: "accepted" })
        await userChoice
      })
    }
  })

  it.each(["granted", "denied", "unsupported"] as const)(
    "requires a fresh contextual request after notification eligibility changes to %s and back",
    async (state) => {
      const view = await renderPrompt()
      requestEducation()
      expect(screen.getByRole("heading", { name: "Notifications" })).toBeVisible()
      if (state === "unsupported") push.supported = false
      else push.permission = state
      view.refresh()
      expect(screen.queryByRole("heading", { name: "Notifications" })).not.toBeInTheDocument()

      push.supported = true
      push.permission = "default"
      view.refresh()
      expect(screen.queryByRole("heading", { name: "Notifications" })).not.toBeInTheDocument()
      requestEducation()
      expect(screen.getByRole("heading", { name: "Notifications" })).toBeVisible()
      expect(push.enable).not.toHaveBeenCalled()
    }
  )

  it.each(["/login", "/register"])(
    "does not revive a contextual request received on %s when returning to events",
    async (path) => {
      window.history.replaceState(null, "", path)
      const view = await renderPrompt()
      requestEducation()
      expect(screen.queryByRole("heading")).not.toBeInTheDocument()
      window.history.replaceState(null, "", "/events")
      view.refresh()
      expect(screen.queryByRole("heading")).not.toBeInTheDocument()
      requestEducation()
      expect(screen.getByRole("heading", { name: "Notifications" })).toBeVisible()
    }
  )

  it("records a dismissal for the new account after switching and leaves the first account eligible", async () => {
    await renderPrompt()
    requestEducation()
    act(() => useAuthStore.setState({ user: { ...user, id: "2" } }))
    expect(screen.queryByRole("heading", { name: "Notifications" })).not.toBeInTheDocument()
    act(() => requestPushEducation("2"))
    fireEvent.click(screen.getByRole("button", { name: "Hide notifications guide" }))
    expect(localStorage.getItem("ecosystem.push.education.dismissedAt:2")).toBe(String(NOW))
    expect(localStorage.getItem("ecosystem.push.education.dismissedAt:1")).toBeNull()
    expect(screen.queryByRole("heading", { name: "Notifications" })).not.toBeInTheDocument()

    act(() => useAuthStore.setState({ user }))
    requestEducation()
    expect(screen.getByRole("heading", { name: "Notifications" })).toBeVisible()
    expect(push.enable).not.toHaveBeenCalled()
  })

  it.each([
    { name: "wide mobile viewport", layoutWidth: 600, viewportWidth: 500, panelWidth: 384 },
    { name: "full-width panned viewport", layoutWidth: 400, viewportWidth: 400, panelWidth: 368 },
  ])(
    "keeps a $name panel aligned with the visible left margin",
    async ({ layoutWidth, viewportWidth, panelWidth }) => {
      const viewport = Object.assign(new EventTarget(), { width: viewportWidth, offsetLeft: 40 })
      Object.defineProperty(window, "visualViewport", { configurable: true, value: viewport })
      Object.defineProperty(document.documentElement, "clientWidth", {
        configurable: true,
        value: layoutWidth,
      })
      const originalMatchMedia = window.matchMedia.bind(window)
      vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
        ...originalMatchMedia(query),
        matches: false,
      }))
      await renderPrompt()
      requestEducation()
      const panel = screen
        .getByRole("heading", { name: "Notifications" })
        .closest<HTMLElement>(".fixed")
      expect(panel).not.toBeNull()
      expect(panel).toHaveStyle({
        left: "56px",
        right: "auto",
        width: `${panelWidth}px`,
      })
    }
  )
})
