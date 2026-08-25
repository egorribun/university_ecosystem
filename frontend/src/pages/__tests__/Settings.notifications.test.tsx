import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ChangeEvent, ReactElement, ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { usePushPreferences } from "@/hooks/usePushPreferences"
import type { User } from "@/types/User"
import i18n from "../../i18n/config"

const tNotifications = (key: string, options?: Record<string, unknown>) =>
  i18n.t(`notifications:${key}`, options)

const AUTH_USER_ID = "123"

const hoistedMocks = vi.hoisted(() => ({
  deleteSubscriptionMock: vi.fn(),
  ensurePushSubscriptionMock: vi.fn(),
  setPushConsentMock: vi.fn(),
  getExistingPushSubscriptionMock: vi.fn(),
  getPersistedTopicsMock: vi.fn(),
  setPersistedTopicsMock: vi.fn(),
  hasPushConsentMock: vi.fn(() => false),
  isPushSupportedMock: vi.fn(() => true),
})) as {
  deleteSubscriptionMock: ReturnType<typeof vi.fn>
  ensurePushSubscriptionMock: ReturnType<typeof vi.fn>
  setPushConsentMock: ReturnType<typeof vi.fn>
  getExistingPushSubscriptionMock: ReturnType<typeof vi.fn>
  getPersistedTopicsMock: ReturnType<typeof vi.fn>
  setPersistedTopicsMock: ReturnType<typeof vi.fn>
  hasPushConsentMock: ReturnType<typeof vi.fn>
  isPushSupportedMock: ReturnType<typeof vi.fn>
}

const authState: { user: User | null } = { user: { id: AUTH_USER_ID } as unknown as User }

vi.mock("@/api/notifications", async () => {
  const actual = await vi.importActual<typeof import("@/api/notifications")>("@/api/notifications")
  return {
    ...actual,
    deleteSubscription: hoistedMocks.deleteSubscriptionMock,
  }
})

vi.mock("@/push/subscribe", async () => {
  const actual = await vi.importActual<typeof import("@/push/subscribe")>("@/push/subscribe")
  return {
    ...actual,
    ensurePushSubscription: hoistedMocks.ensurePushSubscriptionMock,
    setPushConsent: hoistedMocks.setPushConsentMock,
    getExistingPushSubscription: hoistedMocks.getExistingPushSubscriptionMock,
    getPersistedTopics: hoistedMocks.getPersistedTopicsMock,
    setPersistedTopics: hoistedMocks.setPersistedTopicsMock,
    hasPushConsent: hoistedMocks.hasPushConsentMock,
    isPushSupported: hoistedMocks.isPushSupportedMock,
  }
})

vi.mock("@/contexts/AuthContext", async () => {
  const actual =
    await vi.importActual<typeof import("@/contexts/AuthContext")>("@/contexts/AuthContext")
  return {
    ...actual,
    useAuth: () => authState,
  }
})

const {
  deleteSubscriptionMock,
  ensurePushSubscriptionMock,
  setPushConsentMock,
  getExistingPushSubscriptionMock,
  getPersistedTopicsMock,
  setPersistedTopicsMock,
  hasPushConsentMock,
  isPushSupportedMock,
} = hoistedMocks

class MockNotification {
  static permission: NotificationPermission = "default"
}

type MutableSubscription = PushSubscription & {
  toJSON: () => PushSubscriptionJSON
  unsubscribe: () => Promise<boolean>
  __payload: PushSubscriptionJSON
}

const createMockSubscription = (): MutableSubscription => {
  const payload: PushSubscriptionJSON = {
    endpoint: "https://example.com/sub",
    keys: { p256dh: "p256", auth: "auth" },
  }
  return {
    endpoint: payload.endpoint!,
    expirationTime: null,
    options: {
      applicationServerKey: new Uint8Array([1, 2, 3]),
      userVisibleOnly: true,
    },
    toJSON: vi.fn(() => payload),
    unsubscribe: vi.fn(async () => true),
    getKey: vi.fn(() => new ArrayBuffer(0)),
    __payload: payload,
  } as unknown as MutableSubscription
}

type MockRegistration = ServiceWorkerRegistration & {
  pushManager: {
    getSubscription: ReturnType<typeof vi.fn>
    subscribe: ReturnType<typeof vi.fn>
  }
}

let registration: MockRegistration
let queryClient: QueryClient
let wrapper: ({ children }: { children: ReactNode }) => ReactElement

const ensureAtob = () => {
  if (typeof globalThis.atob !== "function") {
    globalThis.atob = (value: string) => Buffer.from(value, "base64").toString("binary")
  }
}

ensureAtob()

beforeEach(() => {
  MockNotification.permission = "default"
  Object.defineProperty(globalThis, "Notification", {
    value: MockNotification,
    configurable: true,
    writable: true,
  })

  authState.user = { id: AUTH_USER_ID } as unknown as User

  const pushManager = {
    getSubscription: vi.fn(),
    subscribe: vi.fn(),
  }

  registration = {
    pushManager,
    showNotification: vi.fn(),
  } as unknown as MockRegistration

  const ready = Promise.resolve(registration)

  Object.defineProperty(navigator, "serviceWorker", {
    value: {
      ready,
      getRegistration: vi.fn(async () => registration),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    },
    configurable: true,
  })

  Object.defineProperty(window, "PushManager", {
    value: function MockPushManager() {},
    configurable: true,
  })

  getExistingPushSubscriptionMock.mockReset()
  getExistingPushSubscriptionMock.mockResolvedValue(null)
  setPushConsentMock.mockReset()
  hasPushConsentMock.mockReset()
  hasPushConsentMock.mockReturnValue(false)
  isPushSupportedMock.mockReset()
  isPushSupportedMock.mockReturnValue(true)
  ensurePushSubscriptionMock.mockReset()
  ensurePushSubscriptionMock.mockResolvedValue(null)
  getPersistedTopicsMock.mockReset()
  getPersistedTopicsMock.mockReturnValue(undefined)
  setPersistedTopicsMock.mockReset()
  deleteSubscriptionMock.mockReset()

  queryClient = new QueryClient()
  wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
})

afterEach(() => {
  vi.clearAllMocks()
  delete (navigator as unknown as Record<string, unknown>).serviceWorker
  delete (window as unknown as Record<string, unknown>).PushManager
  queryClient.clear()
})

describe("usePushPreferences notifications flow", () => {
  it("enables notifications when subscription is ensured", async () => {
    const subscription = createMockSubscription()
    ensurePushSubscriptionMock.mockResolvedValue(subscription)
    getPersistedTopicsMock.mockReturnValue(["news", "schedule"])
    MockNotification.permission = "granted"
    hasPushConsentMock.mockReturnValue(true)

    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))

    expect(ensurePushSubscriptionMock).toHaveBeenCalledTimes(2)
    const initialArgs = ensurePushSubscriptionMock.mock.calls[0]![0]
    expect(initialArgs.requestPermission).toBe(false)
    const ensureArgs = ensurePushSubscriptionMock.mock.calls[1]![0]
    expect(ensureArgs.registration).toBe(registration)
    expect(ensureArgs.requestPermission).toBe(true)
    expect(ensureArgs.topics).toEqual(["news.published", "schedule.changed"])

    expect(setPushConsentMock).toHaveBeenCalledWith(true)
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: tNotifications("messages.enabled"), severity: "success" })
    )
    expect(result.current.topicState).toMatchObject({
      "news.published": true,
      "schedule.changed": true,
      "events.published": false,
      "chat.message.created": false,
      "system.release": false,
    })
  })

  it("disables notifications and removes subscription", async () => {
    const subscription = createMockSubscription()
    ensurePushSubscriptionMock.mockResolvedValue(subscription)
    getPersistedTopicsMock.mockReturnValue(["news", "schedule", "system"])
    MockNotification.permission = "granted"
    hasPushConsentMock.mockReturnValue(true)
    registration.pushManager.getSubscription.mockResolvedValue(subscription)

    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(subscription.unsubscribe).toHaveBeenCalled()
    expect(deleteSubscriptionMock).toHaveBeenCalledWith(subscription.endpoint)
    expect(setPushConsentMock).toHaveBeenCalledWith(false)
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: tNotifications("messages.disabled"), severity: "success" })
    )
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(false))
  })

  it("updates topics when toggles change", async () => {
    const subscription = createMockSubscription()
    ensurePushSubscriptionMock
      .mockResolvedValueOnce(subscription)
      .mockResolvedValueOnce(subscription)
    getPersistedTopicsMock
      .mockReturnValueOnce(["news", "schedule", "system"])
      .mockReturnValueOnce(["news", "schedule"])
    MockNotification.permission = "granted"
    hasPushConsentMock.mockReturnValue(true)

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))

    const handler = result.current.handleTopicToggle("system.release")
    await act(async () => {
      await handler({} as ChangeEvent<HTMLInputElement>, false)
    })

    expect(ensurePushSubscriptionMock).toHaveBeenCalledTimes(2)
    const updateArgs = ensurePushSubscriptionMock.mock.calls[1]![0]
    expect(updateArgs.topics).toEqual(["news.published", "schedule.changed"])
    expect(setPersistedTopicsMock).toHaveBeenCalledWith(
      ["news.published", "schedule.changed"],
      expect.objectContaining({ userId: AUTH_USER_ID })
    )
    expect(result.current.topicState["system.release"]).toBe(false)
  })

  it("persists topic selection locally when notifications are disabled", async () => {
    ensurePushSubscriptionMock.mockResolvedValue(null)

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    expect(result.current.notificationsEnabled).toBe(false)

    const handler = result.current.handleTopicToggle("news.published")
    await act(async () => {
      await handler({} as ChangeEvent<HTMLInputElement>, false)
    })

    expect(setPersistedTopicsMock).toHaveBeenCalledWith(
      ["schedule.changed", "events.published", "chat.message.created", "system.release"],
      expect.objectContaining({ userId: AUTH_USER_ID })
    )
    expect(result.current.topicState["news.published"]).toBe(false)
  })

  it("notifies user when permission is denied", async () => {
    ensurePushSubscriptionMock.mockResolvedValue(null)
    MockNotification.permission = "denied"

    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(ensurePushSubscriptionMock).toHaveBeenCalled()
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: tNotifications("messages.enableInSettings"),
        severity: "info",
      })
    )
    expect(result.current.notificationsEnabled).toBe(false)
    expect(result.current.notificationPermission).toBe("denied")
  })

  it("asks user to confirm permission prompt when subscription is unavailable", async () => {
    ensurePushSubscriptionMock.mockResolvedValue(null)
    MockNotification.permission = "default"

    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: tNotifications("messages.confirmPermission"),
        severity: "info",
      })
    )
    expect(result.current.notificationsEnabled).toBe(false)
    expect(result.current.notificationPermission).toBe("default")
  })

  it("informs user when subscription cannot be created despite granted permission", async () => {
    ensurePushSubscriptionMock.mockResolvedValue(null)
    MockNotification.permission = "granted"

    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: tNotifications("messages.subscriptionFailed"),
        severity: "error",
      })
    )
    expect(result.current.notificationsEnabled).toBe(false)
    expect(result.current.notificationPermission).toBe("granted")
  })
})
