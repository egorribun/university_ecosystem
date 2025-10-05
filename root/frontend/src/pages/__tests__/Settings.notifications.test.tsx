import { act, renderHook, waitFor } from "@testing-library/react"
import type { ChangeEvent } from "react"
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest"
import { usePushPreferences } from "@/hooks/usePushPreferences"

const hoistedMocks = vi.hoisted(() => ({
  getVapidKeyMock: vi.fn(),
  saveSubscriptionMock: vi.fn(),
  deleteSubscriptionMock: vi.fn(),
  updateSubscriptionTopicsMock: vi.fn(),
  setPushConsentMock: vi.fn(),
  getExistingPushSubscriptionMock: vi.fn(),
  isPushSupportedMock: vi.fn(() => true),
  requestPermissionMock: vi.fn(),
})) as {
  getVapidKeyMock: ReturnType<typeof vi.fn>
  saveSubscriptionMock: ReturnType<typeof vi.fn>
  deleteSubscriptionMock: ReturnType<typeof vi.fn>
  updateSubscriptionTopicsMock: ReturnType<typeof vi.fn>
  setPushConsentMock: ReturnType<typeof vi.fn>
  getExistingPushSubscriptionMock: ReturnType<typeof vi.fn>
  isPushSupportedMock: ReturnType<typeof vi.fn>
  requestPermissionMock: ReturnType<typeof vi.fn>
}

vi.mock("@/api/notifications", async () => {
  const actual = await vi.importActual<typeof import("@/api/notifications")>("@/api/notifications")
  return {
    ...actual,
    getVapidKey: hoistedMocks.getVapidKeyMock,
    saveSubscription: hoistedMocks.saveSubscriptionMock,
    deleteSubscription: hoistedMocks.deleteSubscriptionMock,
    updateSubscriptionTopics: hoistedMocks.updateSubscriptionTopicsMock,
  }
})

vi.mock("@/push/subscribe", async () => {
  const actual = await vi.importActual<typeof import("@/push/subscribe")>("@/push/subscribe")
  return {
    ...actual,
    setPushConsent: hoistedMocks.setPushConsentMock,
    getExistingPushSubscription: hoistedMocks.getExistingPushSubscriptionMock,
    isPushSupported: hoistedMocks.isPushSupportedMock,
  }
})

const {
  getVapidKeyMock,
  saveSubscriptionMock,
  deleteSubscriptionMock,
  updateSubscriptionTopicsMock,
  setPushConsentMock,
  getExistingPushSubscriptionMock,
  isPushSupportedMock,
  requestPermissionMock,
} = hoistedMocks

class MockNotification {
  static permission: NotificationPermission = "default"

  static requestPermission = requestPermissionMock
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

const ensureAtob = () => {
  if (typeof globalThis.atob !== "function") {
    globalThis.atob = (value: string) => Buffer.from(value, "base64").toString("binary")
  }
}

ensureAtob()

beforeEach(() => {
  requestPermissionMock.mockReset()
  MockNotification.permission = "default"
  Object.defineProperty(globalThis, "Notification", {
    value: MockNotification,
    configurable: true,
    writable: true,
  })

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
  isPushSupportedMock.mockReset()
  isPushSupportedMock.mockReturnValue(true)
  getVapidKeyMock.mockReset()
  saveSubscriptionMock.mockReset()
  deleteSubscriptionMock.mockReset()
  updateSubscriptionTopicsMock.mockReset()
})

afterEach(() => {
  vi.clearAllMocks()
  delete (navigator as any).serviceWorker
  delete (window as any).PushManager
})

describe("usePushPreferences notifications flow", () => {
  it("requests permission and enables notifications", async () => {
    const subscription = createMockSubscription()
    registration.pushManager.getSubscription.mockResolvedValueOnce(null)
    registration.pushManager.subscribe.mockResolvedValue(subscription)

    requestPermissionMock.mockImplementation(async () => {
      MockNotification.permission = "granted"
      return "granted"
    })

    getVapidKeyMock.mockResolvedValue("BElq1234ABCD5678")
    saveSubscriptionMock.mockResolvedValue({ topics: ["news", "schedule"] })

    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }))

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(requestPermissionMock).toHaveBeenCalled()
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))

    expect(registration.pushManager.subscribe).toHaveBeenCalledWith(
      expect.objectContaining({ userVisibleOnly: true }),
    )
    expect(saveSubscriptionMock).toHaveBeenCalledWith(subscription.__payload, [
      "news",
      "schedule",
      "system",
    ])
    expect(setPushConsentMock).toHaveBeenCalledWith(true)
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "Уведомления включены", sev: "success" }),
    )
    expect(result.current.topicState).toMatchObject({ news: true, schedule: true, system: false })
  })

  it("disables notifications and removes subscription", async () => {
    const subscription = createMockSubscription()
    registration.pushManager.getSubscription.mockResolvedValue(subscription)
    getExistingPushSubscriptionMock.mockResolvedValue(subscription)
    saveSubscriptionMock.mockResolvedValue({ topics: ["news", "schedule", "system"] })

    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }))

    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(subscription.unsubscribe).toHaveBeenCalled()
    expect(deleteSubscriptionMock).toHaveBeenCalledWith(subscription.endpoint)
    expect(setPushConsentMock).toHaveBeenCalledWith(false)
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "Уведомления выключены", sev: "success" }),
    )
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(false))
  })

  it("updates topics when toggles change", async () => {
    const subscription = createMockSubscription()
    registration.pushManager.getSubscription.mockResolvedValue(subscription)
    getExistingPushSubscriptionMock.mockResolvedValue(subscription)
    saveSubscriptionMock.mockResolvedValue({ topics: ["news", "schedule", "system"] })
    updateSubscriptionTopicsMock.mockResolvedValue({ topics: ["news", "schedule"] })

    const { result } = renderHook(() => usePushPreferences())

    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))

    const handler = result.current.handleTopicToggle("system")
    await act(async () => {
      await handler({} as ChangeEvent<HTMLInputElement>, false)
    })

    expect(updateSubscriptionTopicsMock).toHaveBeenCalledWith(subscription.endpoint, [
      "news",
      "schedule",
    ])
    expect(result.current.topicState.system).toBe(false)
  })

  it("notifies user when permission is denied", async () => {
    registration.pushManager.getSubscription.mockResolvedValue(null)

    requestPermissionMock.mockImplementation(async () => {
      MockNotification.permission = "denied"
      return "denied"
    })

    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }))

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(requestPermissionMock).toHaveBeenCalled()
    expect(getVapidKeyMock).not.toHaveBeenCalled()
    expect(saveSubscriptionMock).not.toHaveBeenCalled()
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "Разрешите уведомления в настройках браузера", sev: "info" }),
    )
    expect(result.current.notificationsEnabled).toBe(false)
    expect(result.current.notificationPermission).toBe("denied")
  })
})
