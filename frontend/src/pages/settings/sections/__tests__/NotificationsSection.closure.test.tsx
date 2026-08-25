import { fireEvent, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const pushState = vi.hoisted(() => ({
  value: {
    pushSupported: true,
    notificationPermission: "default" as NotificationPermission,
    notificationsEnabled: false,
    pushBusy: false,
    pushInitializing: false,
    permissionText: "not requested",
    enableNotifications: vi.fn(),
    disableNotifications: vi.fn(),
  },
}))

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: () => pushState.value,
}))

import i18n from "@/i18n/config"
import { NotificationsSection } from "@/pages/settings/sections/NotificationsSection"

const createProps = () => ({
  setSnackbar: vi.fn(),
  dndEnabled: true,
  dndStart: "22:00",
  dndEnd: "07:00",
  dndSaving: false,
  onDndToggle: vi.fn(),
  onDndStartChange: vi.fn(),
  onDndStartBlur: vi.fn(),
  onDndEndChange: vi.fn(),
  onDndEndBlur: vi.fn(),
})

const openNotificationAccordion = () => {
  const button = screen.getByRole("button", { name: /notifications\.push\.title/ })
  if (button.getAttribute("aria-expanded") !== "true") {
    fireEvent.click(button)
  }
}

const renderSection = async (overrides: Partial<ReturnType<typeof createProps>> = {}) => {
  const props = { ...createProps(), ...overrides }
  const result = await renderWithRouter({
    ui: () => <NotificationsSection {...props} />,
    authProvider: false,
  })
  // AccordionSection intentionally starts collapsed; expose its branch content.
  openNotificationAccordion()
  return { ...result, props, openNotificationAccordion }
}

beforeEach(async () => {
  await i18n.changeLanguage("en")
  pushState.value = {
    pushSupported: true,
    notificationPermission: "default",
    notificationsEnabled: false,
    pushBusy: false,
    pushInitializing: false,
    permissionText: "not requested",
    enableNotifications: vi.fn(),
    disableNotifications: vi.fn(),
  }
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("NotificationsSection — push and quiet-hours branches", () => {
  it("renders initialization, unsupported, and denied permission states", async () => {
    pushState.value.pushInitializing = true
    const { rerender } = await renderSection()
    expect(screen.getByText("notifications.loading")).toBeInTheDocument()

    pushState.value = { ...pushState.value, pushInitializing: false, pushSupported: false }
    rerender(<NotificationsSection {...createProps()} />)
    expect(screen.getByText("notifications.notSupported")).toBeInTheDocument()

    pushState.value = {
      ...pushState.value,
      pushSupported: true,
      notificationPermission: "denied",
      permissionText: "blocked",
    }
    rerender(<NotificationsSection {...createProps()} />)
    expect(screen.getByText(/Current status/)).toBeInTheDocument()
  })

  it("toggles notifications, handles busy guards, and updates DND controls", async () => {
    const { props, rerender, openNotificationAccordion } = await renderSection()
    const switches = screen.getAllByRole("switch")
    expect(switches).toHaveLength(2)

    fireEvent.click(switches[0]!)
    expect(pushState.value.enableNotifications).toHaveBeenCalledOnce()

    pushState.value = { ...pushState.value, notificationsEnabled: true, pushBusy: true }
    rerender(<NotificationsSection {...props} />)
    openNotificationAccordion()
    expect(screen.getAllByRole("switch")[0]).toBeDisabled()
    fireEvent.click(screen.getAllByRole("switch")[0]!)
    expect(pushState.value.disableNotifications).not.toHaveBeenCalled()

    pushState.value = { ...pushState.value, pushBusy: false }
    rerender(<NotificationsSection {...props} />)
    openNotificationAccordion()
    fireEvent.click(screen.getAllByRole("switch")[0]!)
    expect(pushState.value.disableNotifications).toHaveBeenCalledOnce()

    fireEvent.click(screen.getAllByRole("switch")[1]!)
    expect(props.onDndToggle).toHaveBeenCalledWith(expect.anything(), false)

    const timeInputs = screen.getAllByDisplayValue(/:/)
    expect(timeInputs).toHaveLength(2)
    fireEvent.change(timeInputs[0]!, { target: { value: "21:30" } })
    fireEvent.blur(timeInputs[0]!)
    fireEvent.change(timeInputs[1]!, { target: { value: "06:30" } })
    fireEvent.blur(timeInputs[1]!)
    expect(props.onDndStartChange).toHaveBeenCalled()
    expect(props.onDndStartBlur).toHaveBeenCalled()
    expect(props.onDndEndChange).toHaveBeenCalled()
    expect(props.onDndEndBlur).toHaveBeenCalled()

    rerender(<NotificationsSection {...props} dndEnabled={false} dndSaving />)
    openNotificationAccordion()
    expect(screen.getAllByRole("switch")[1]).toBeDisabled()
    expect(screen.getAllByDisplayValue(/:/)[0]).toBeDisabled()
  })
})
