import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import InstallPrompt from "@/components/pwa/InstallPrompt"
import { useAuthStore } from "@/stores/useAuthStore"
import type { User } from "@/types/User"
import { requestPushEducation } from "@/app/pwaEvents"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
  Trans: ({ i18nKey }: { i18nKey: string }) => i18nKey,
}))

const pushState = vi.hoisted(() => ({
  supported: true,
  permission: "default" as NotificationPermission,
  enable: vi.fn(),
}))
vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: () => ({
    topicKeys: [],
    topicState: {},
    pushSupported: pushState.supported,
    notificationPermission: pushState.permission,
    notificationsEnabled: false,
    pushBusy: false,
    pushInitializing: false,
    permissionText: "default",
    enableNotifications: pushState.enable,
    disableNotifications: vi.fn(),
    handleTopicToggle: vi.fn(),
    safariIOS: false,
    safariGuideUrl: "",
  }),
}))

const requestEducation = (userId = "1") => act(() => requestPushEducation(userId))
const user: User = { id: "1", email: "student@example.test", is_active: true }

describe("contextual push education", () => {
  beforeEach(() => {
    localStorage.clear()
    pushState.supported = true
    pushState.permission = "default"
    pushState.enable.mockClear()
    useAuthStore.setState({ user: null, loading: false })
    window.history.replaceState(null, "", "/events")
  })

  it("does not appear automatically for an authenticated user", () => {
    useAuthStore.setState({ user })
    render(<InstallPrompt />)
    expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()
    expect(pushState.enable).not.toHaveBeenCalled()
  })

  it("appears after a contextual request from an authenticated event action", () => {
    useAuthStore.setState({ user })
    render(<InstallPrompt />)
    requestEducation()
    expect(screen.getByText("system:installPrompt.notificationsTitle")).toBeInTheDocument()
    expect(pushState.enable).not.toHaveBeenCalled()
  })

  it("retains a contextual request until the deferred panel mounts", () => {
    useAuthStore.setState({ user })
    requestPushEducation(user.id)
    render(<InstallPrompt />)
    expect(screen.getByText("system:installPrompt.notificationsTitle")).toBeInTheDocument()
  })

  it("ignores a queued registration request for another account", () => {
    useAuthStore.setState({ user: { ...user, id: "2" } })
    render(<InstallPrompt />)
    requestEducation()
    expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()
  })

  it.each([
    ["anonymous", null, "default", true, "/events"],
    ["login", user, "default", true, "/login"],
    ["denied", user, "denied", true, "/events"],
    ["unsupported", user, "default", false, "/events"],
    ["granted", user, "granted", true, "/events"],
  ] as const)("never shows on %s context", (_name, user, permission, supported, path) => {
    useAuthStore.setState({ user })
    pushState.permission = permission
    pushState.supported = supported
    window.history.replaceState(null, "", path)
    render(<InstallPrompt />)
    requestEducation()
    expect(screen.queryByText("system:installPrompt.notificationsTitle")).not.toBeInTheDocument()
    expect(pushState.enable).not.toHaveBeenCalled()
  })

  it("does not transfer one account's dismissal to another account", () => {
    useAuthStore.setState({ user })
    const { rerender } = render(<InstallPrompt />)
    requestEducation()
    fireEvent.click(screen.getByRole("button", { name: "system:installPrompt.notificationsClose" }))
    expect(localStorage.getItem("ecosystem.push.education.dismissedAt:1")).not.toBeNull()

    act(() => useAuthStore.setState({ user: { ...user, id: "2" } }))
    rerender(<InstallPrompt />)
    requestEducation("2")
    expect(screen.getByText("system:installPrompt.notificationsTitle")).toBeInTheDocument()
  })

  it("keeps the contextual close action at the 44px touch-target floor", () => {
    useAuthStore.setState({ user })
    render(<InstallPrompt />)
    requestEducation()
    expect(
      screen.getByRole("button", { name: "system:installPrompt.notificationsClose" })
    ).toHaveClass("min-h-11", "min-w-11")
  })
})
