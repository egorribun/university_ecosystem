import { fireEvent, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const topicApi = vi.hoisted(() => () => {
  const topicKeys = [
    "news.published",
    "schedule.changed",
    "events.published",
    "chat.message.created",
    "system.release",
  ] as const
  const toggle = vi.fn()
  return {
    topicKeys: [...topicKeys],
    topicState: Object.fromEntries(topicKeys.map((key) => [key, key !== "chat.message.created"])),
    topicLabels: Object.fromEntries(topicKeys.map((key) => [key, `Topic ${key}`])),
    topicsReady: true,
    topicToggle: toggle,
    handleTopicToggle: vi.fn(
      (key: string) => (_event: unknown, checked: boolean) => toggle(key, checked)
    ),
  }
})

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
    ...topicApi(),
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
  // The shared test setup initializes the real i18n instance to English, so
  // target the translated accessible accordion name rather than its key.
  const button = screen.getByRole("button", {
    name: /^Push notifications Receive timely updates about your university activity\.$/,
  })
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
    ...topicApi(),
  }
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("NotificationsSection — push and quiet-hours branches", () => {
  it("renders initialization, unsupported, and denied permission states", async () => {
    pushState.value.pushInitializing = true
    const { rerender } = await renderSection()
    expect(screen.getByText("Loading notification settings…")).toBeInTheDocument()

    pushState.value = { ...pushState.value, pushInitializing: false, pushSupported: false }
    rerender(<NotificationsSection {...createProps()} />)
    expect(
      screen.getByText("Push notifications are not supported in this browser.")
    ).toBeInTheDocument()

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
    expect(screen.getAllByRole("switch")).toHaveLength(7)

    fireEvent.click(screen.getByRole("switch", { name: "Turn on notifications" }))
    expect(pushState.value.enableNotifications).toHaveBeenCalledOnce()

    pushState.value = { ...pushState.value, notificationsEnabled: true, pushBusy: true }
    rerender(<NotificationsSection {...props} />)
    openNotificationAccordion()
    expect(screen.getByRole("switch", { name: "Turn on notifications" })).toBeDisabled()
    fireEvent.click(screen.getByRole("switch", { name: "Turn on notifications" }))
    expect(pushState.value.disableNotifications).not.toHaveBeenCalled()

    pushState.value = { ...pushState.value, pushBusy: false }
    rerender(<NotificationsSection {...props} />)
    openNotificationAccordion()
    fireEvent.click(screen.getByRole("switch", { name: "Turn on notifications" }))
    expect(pushState.value.disableNotifications).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByRole("switch", { name: "Turn on quiet hours" }))
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
    expect(screen.getByRole("switch", { name: "Turn on quiet hours" })).toBeDisabled()
    expect(screen.getAllByDisplayValue(/:/)[0]).toBeDisabled()
  })

  it("groups the five canonical topics and toggles each one", async () => {
    await renderSection()

    const group = screen.getByRole("group", { name: "Notification topics" })
    expect(group).toBeInTheDocument()
    expect(
      screen.getByText("Your topic choice applies once you turn notifications on.")
    ).toBeInTheDocument()
    const chat = screen.getByRole("switch", { name: "Topic chat.message.created" })
    expect(chat).not.toBeChecked()
    expect(chat).toBeEnabled()
    expect(screen.getByRole("switch", { name: "Topic news.published" })).toBeChecked()

    fireEvent.click(chat)

    expect(pushState.value.handleTopicToggle).toHaveBeenCalledWith("chat.message.created")
    expect(pushState.value.topicToggle).toHaveBeenCalledWith("chat.message.created", true)
  })

  it("explains that topics apply to every device once notifications are on", async () => {
    pushState.value = { ...pushState.value, notificationsEnabled: true }
    await renderSection()

    expect(
      screen.getByText(
        "Choose what push notifications are about. Your choice applies to all your devices."
      )
    ).toBeInTheDocument()
  })

  it("locks topic toggles until the saved preference has loaded", async () => {
    pushState.value = { ...pushState.value, topicsReady: false }
    await renderSection()

    expect(screen.getByRole("switch", { name: "Topic news.published" })).toBeDisabled()
  })

  it("locks topic toggles while push is busy", async () => {
    pushState.value = { ...pushState.value, pushBusy: true }
    await renderSection()

    expect(screen.getByRole("switch", { name: "Topic system.release" })).toBeDisabled()
  })
})
