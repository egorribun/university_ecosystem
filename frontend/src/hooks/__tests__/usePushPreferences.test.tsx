import { renderHook, act, waitFor } from "@testing-library/react"
import type { PushTopicsResponse } from "@/types/notifications"
import { useAuthStore } from "@/stores/useAuthStore"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import type { ReactNode } from "react"
import { createElement } from "react"

// ---- Module mocks (NEVER hit MSW for /api/ paths) ----
const mockDeleteSubscription = vi.fn(async (..._a: unknown[]) => undefined)
const mockFetchPushTopics = vi.fn(async (): Promise<PushTopicsResponse> => serverTopics(false))
const mockUpdatePushTopics = vi.fn(async (..._a: unknown[]) => undefined)
vi.mock("@/api/notifications", () => ({
  deleteSubscription: (...args: unknown[]) => mockDeleteSubscription(...args),
  fetchPushTopics: () => mockFetchPushTopics(),
  updatePushTopics: (...args: unknown[]) => mockUpdatePushTopics(...args),
}))

function serverTopics(hasPreferences: boolean, topics: string[] = []): PushTopicsResponse {
  return {
    allowed: [...ALL_TOPICS],
    topics,
    has_preferences: hasPreferences,
    updated_at: null,
  }
}

const mockLogError = vi.fn((..._a: unknown[]) => undefined)
const mockLogWarning = vi.fn((..._a: unknown[]) => undefined)
vi.mock("@/app/logger", () => ({
  logError: (...args: unknown[]) => mockLogError(...args),
  logWarning: (...args: unknown[]) => mockLogWarning(...args),
}))

const mockIsPushSupported = vi.fn(() => true)
const mockResolveServiceWorkerRegistration = vi.fn(async (..._a: unknown[]) => null as any)
const mockEnsurePushSubscription = vi.fn(async (..._a: unknown[]) => null as any)
const mockSetPushConsent = vi.fn((..._a: unknown[]) => undefined)
const mockGetPersistedTopics = vi.fn((..._a: unknown[]) => undefined as any)
const mockGetExistingPushSubscription = vi.fn(async (..._a: unknown[]) => null as any)
const mockHasPushConsent = vi.fn(() => false)
const mockSetPersistedTopics = vi.fn((..._a: unknown[]) => undefined)
vi.mock("@/push/subscribe", () => ({
  isPushSupported: () => mockIsPushSupported(),
  resolveServiceWorkerRegistration: (...args: unknown[]) =>
    mockResolveServiceWorkerRegistration(...args),
  ensurePushSubscription: (...args: unknown[]) => mockEnsurePushSubscription(...args),
  setPushConsent: (...args: unknown[]) => mockSetPushConsent(...args),
  getPersistedTopics: (...args: unknown[]) => mockGetPersistedTopics(...args),
  getOwnedPushSubscription: (...args: unknown[]) => mockGetExistingPushSubscription(...args),
  hasPushConsent: () => mockHasPushConsent(),
  setPersistedTopics: (...args: unknown[]) => mockSetPersistedTopics(...args),
}))

vi.mock("@/contexts/AuthContext", () => ({
  currentUserQueryKey: ["users", "me"] as const,
}))

const ALL_TOPICS = [
  "news.published",
  "schedule.changed",
  "events.published",
  "chat.message.created",
  "system.release",
] as const

const setIdentity = (id: unknown, loading = false) =>
  useAuthStore.setState({ user: id === null ? null : ({ id } as any), loading })

const topicStateOf = (enabled: readonly string[]) =>
  Object.fromEntries(ALL_TOPICS.map((topic) => [topic, enabled.includes(topic)]))

function never<T>(): Promise<T> {
  return new Promise<T>(() => {})
}

const mockIsSafariIOS = vi.fn(() => false)
vi.mock("@/utils/browser", () => ({
  isSafariIOS: () => mockIsSafariIOS(),
}))

// IMPORTANT: useTranslation must return a STABLE object/`t` reference across renders.
// `t` is a dependency of the detectSubscription effect (which calls setState); a fresh
// `t` per render re-runs that effect → infinite render loop → heap OOM.
const stableT = (k: string, opts?: Record<string, unknown>) =>
  opts && "label" in opts ? `${k}:${String(opts.label)}` : k
const stableTranslation = {
  t: stableT,
  i18n: { language: "en", changeLanguage: () => Promise.resolve() },
}
vi.mock("react-i18next", () => ({
  useTranslation: () => stableTranslation,
}))

import { NOTIFICATION_TOPIC_KEYS, usePushPreferences } from "../usePushPreferences"

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
  return createElement(QueryClientProvider, { client }, children)
}

// Helper to install a Notification global with a controllable permission
function installNotification(permission: NotificationPermission) {
  ;(globalThis as any).Notification = {
    permission,
    requestPermission: vi.fn(async () => permission),
  }
}

describe("usePushPreferences", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsPushSupported.mockReturnValue(true)
    mockResolveServiceWorkerRegistration.mockResolvedValue(null)
    mockEnsurePushSubscription.mockResolvedValue(null)
    mockGetPersistedTopics.mockReturnValue(undefined)
    mockGetExistingPushSubscription.mockResolvedValue(null)
    mockHasPushConsent.mockReturnValue(false)
    mockIsSafariIOS.mockReturnValue(false)
    // Hydration is exercised explicitly; elsewhere it must not race toggles.
    mockFetchPushTopics.mockReturnValue(never())
    mockUpdatePushTopics.mockResolvedValue(undefined)
    setIdentity(7)
    installNotification("default")
    // Clean navigator.permissions to a no-op so the permission effect doesn't query.
    delete (globalThis.navigator as any).permissions
  })

  afterEach(() => {
    delete (globalThis as any).Notification
    delete (globalThis.navigator as any).permissions
  })

  it("returns defaults + derived values (selectedTopicsDescription with all topics)", async () => {
    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    // All five default topics are selected → description is a join of labels.
    expect(result.current.selectedTopicsDescription).toContain(
      "notifications:topics.scheduleChanged"
    )
    expect(result.current.permissionText).toBe("notifications:permission.default")
    expect(result.current.safariGuideUrl).toContain("support.apple.com")

    // detectSubscription effect resolves → pushInitializing flips false (lines 410-463 happy path)
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
  })

  // ---- enableNotifications branches (lines 150-216) ----

  it("requests native permission before awaiting service-worker readiness", async () => {
    const notification = {
      permission: "default" as NotificationPermission,
      requestPermission: vi.fn(async () => {
        notification.permission = "granted"
        return "granted" as NotificationPermission
      }),
    }
    vi.stubGlobal("Notification", notification)
    let permissionRequestsAtReadiness = -1
    mockResolveServiceWorkerRegistration.mockImplementation(async () => {
      permissionRequestsAtReadiness = notification.requestPermission.mock.calls.length
      return {} as ServiceWorkerRegistration
    })
    mockEnsurePushSubscription.mockResolvedValue(null)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await act(async () => {
      const enabling = result.current.enableNotifications()
      expect(notification.requestPermission).toHaveBeenCalledOnce()
      await enabling
    })

    expect(permissionRequestsAtReadiness).toBe(1)
    expect(notification.requestPermission).toHaveBeenCalledOnce()
    expect(mockEnsurePushSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ requestPermission: false })
    )
  })

  it("enableNotifications: unsupported push → warning + setPushSupported(false) (152-159)", async () => {
    mockIsPushSupported.mockReturnValue(false)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.browserUnsupported" })
    )
    await waitFor(() => expect(result.current.pushSupported).toBe(false))
  })

  it("enableNotifications: Notification undefined → notificationsUnsupported (156-159)", async () => {
    // push supported true (re-enable after detect effect) but Notification missing
    mockIsPushSupported.mockReturnValue(true)
    delete (globalThis as any).Notification
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.notificationsUnsupported" })
    )
  })

  it("enableNotifications: no SW registration → workerNotReady (167-171)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue(null)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.workerNotReady", severity: "info" })
    )
  })

  it("enableNotifications: subscription null + permission denied → enableInSettings (179-189)", async () => {
    installNotification("denied")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue(null)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.enableInSettings",
        severity: "info",
      })
    )
  })

  it("enableNotifications: subscription null + permission granted → subscriptionFailed error (179-189)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue(null)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.subscriptionFailed",
        severity: "error",
      })
    )
  })

  it.each([
    ["denied", "notifications:messages.enableInSettings"],
    ["default", "notifications:messages.confirmPermission"],
  ] as const)(
    "reports a %s permission revoked while subscription was pending",
    async (permission, text) => {
      installNotification("granted")
      mockResolveServiceWorkerRegistration.mockResolvedValue({} as ServiceWorkerRegistration)
      mockEnsurePushSubscription.mockImplementation(async () => {
        ;(globalThis as any).Notification.permission = permission
        return null
      })
      const onNotify = vi.fn()
      const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

      await act(async () => {
        await result.current.enableNotifications()
      })

      expect(onNotify).toHaveBeenCalledWith(expect.objectContaining({ text, severity: "info" }))
      expect(result.current.pushSubscription).toBeNull()
      expect(result.current.notificationPermission).toBe(permission)
    }
  )

  it("enableNotifications: subscription null + undecided permission asks for confirmation", async () => {
    installNotification("default")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue(null)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.confirmPermission",
        severity: "info",
      })
    )
  })

  it("does not await service-worker readiness when the native permission request rejects", async () => {
    const onNotify = vi.fn()
    const notification = {
      permission: "default" as NotificationPermission,
      requestPermission: vi.fn(async () => {
        throw new DOMException("Not allowed", "NotAllowedError")
      }),
    }
    vi.stubGlobal("Notification", notification)
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(notification.requestPermission).toHaveBeenCalledOnce()
    expect(mockResolveServiceWorkerRegistration).not.toHaveBeenCalled()
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.enableFailed", severity: "error" })
    )
    expect(result.current.pushBusy).toBe(false)
    expect(result.current.notificationsEnabled).toBe(false)
  })

  it("enableNotifications: subscription present but permission not granted → enableInSettings (191-199)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockImplementation(async () => {
      ;(globalThis as any).Notification.permission = "denied"
      return { endpoint: "https://x" } as any
    })
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.enableInSettings",
        severity: "info",
      })
    )
  })

  it("enableNotifications: full success path → enabled + setPushConsent (200-205)", async () => {
    installNotification("granted")
    const registration = {} as ServiceWorkerRegistration
    mockResolveServiceWorkerRegistration.mockResolvedValue(registration)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    mockGetPersistedTopics.mockReturnValue(["news", "events"])
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    // Enabling never chooses topics implicitly: the server keeps the
    // account's canonical preference, including an explicit opt-out.
    expect(mockEnsurePushSubscription).toHaveBeenCalledWith({
      registration,
      requestPermission: false,
    })
    expect(mockUpdatePushTopics).not.toHaveBeenCalled()
    expect(mockSetPushConsent).toHaveBeenCalledWith(true)
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.enabled", severity: "success" })
    )
    await waitFor(() => expect(result.current.pushSubscription).not.toBeNull())
  })

  it("enableNotifications: thrown error → enableFailed + logError (206-209)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockRejectedValue(new Error("boom"))
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(mockLogError).toHaveBeenCalledWith("Failed to enable notifications", expect.anything())
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.enableFailed", severity: "error" })
    )
  })

  it("sends topics toggled while disabled as an explicit update after binding", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))

    await act(async () => {
      await result.current.handleTopicToggle("news.published")({} as any, false)
    })
    expect(mockUpdatePushTopics).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(mockEnsurePushSubscription).toHaveBeenCalledWith(
      expect.not.objectContaining({ topics: expect.anything() })
    )
    expect(mockUpdatePushTopics).toHaveBeenCalledOnce()
    expect(mockUpdatePushTopics).toHaveBeenCalledWith(
      "https://x",
      ALL_TOPICS.filter((topic) => topic !== "news.published")
    )
    expect(mockSetPushConsent).toHaveBeenCalledWith(true)

    // The pending choice is consumed once it reached the server.
    await act(async () => {
      await result.current.enableNotifications()
    })
    expect(mockUpdatePushTopics).toHaveBeenCalledOnce()
  })

  it("sends an all-off choice made while disabled as an explicit empty update", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))

    for (const topic of ALL_TOPICS) {
      await act(async () => {
        await result.current.handleTopicToggle(topic)({} as any, false)
      })
    }
    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(mockUpdatePushTopics).toHaveBeenCalledWith("https://x", [])
  })

  it("drops a pending topic choice when another account is confirmed", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    await act(async () => {
      await result.current.handleTopicToggle("news.published")({} as any, false)
    })

    act(() => {
      setIdentity(8)
    })
    await waitFor(() => expect(mockGetExistingPushSubscription).toHaveBeenCalledTimes(2))
    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(mockEnsurePushSubscription).toHaveBeenCalledOnce()
    expect(mockUpdatePushTopics).not.toHaveBeenCalled()
  })

  it("keeps a pending topic choice when its explicit update fails", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    mockUpdatePushTopics.mockRejectedValueOnce(new Error("patch failed"))
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    await act(async () => {
      await result.current.handleTopicToggle("system.release")({} as any, false)
    })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.enableFailed", severity: "error" })
    )
    expect(mockSetPushConsent).not.toHaveBeenCalledWith(true)
    expect(result.current.pushSubscription).toBeNull()

    await act(async () => {
      await result.current.enableNotifications()
    })
    expect(mockUpdatePushTopics).toHaveBeenCalledTimes(2)
    expect(mockUpdatePushTopics).toHaveBeenLastCalledWith(
      "https://x",
      ALL_TOPICS.filter((topic) => topic !== "system.release")
    )
  })

  it("does not grant push consent when subscription persistence fails", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockRejectedValue(new Error("persistence failed"))
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(mockSetPushConsent).not.toHaveBeenCalledWith(true)
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.enableFailed", severity: "error" })
    )
  })

  // ---- disableNotifications branches (lines 218-276) ----

  it("disableNotifications: unsupported → clears state without notify (222-227)", async () => {
    mockIsPushSupported.mockReturnValue(false)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(mockSetPushConsent).toHaveBeenCalledWith(false)
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("disableNotifications: no SW registration → workerUnavailable (231-235)", async () => {
    mockIsPushSupported.mockReturnValue(true)
    mockResolveServiceWorkerRegistration.mockResolvedValue(null)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.workerUnavailable",
        severity: "warning",
      })
    )
  })

  it("disableNotifications: no active subscription → disabled success (238-244)", async () => {
    mockIsPushSupported.mockReturnValue(true)
    mockResolveServiceWorkerRegistration.mockResolvedValue({
      pushManager: { getSubscription: vi.fn(async () => null) },
    } as any)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(mockSetPushConsent).toHaveBeenCalledWith(false)
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.disabled", severity: "success" })
    )
  })

  it("disableNotifications: unsubscribe + delete success → disabled (245-266)", async () => {
    mockIsPushSupported.mockReturnValue(true)
    const sub = {
      endpoint: "https://endpoint",
      unsubscribe: vi.fn(async () => true),
    }
    mockResolveServiceWorkerRegistration.mockResolvedValue({
      pushManager: { getSubscription: vi.fn(async () => sub) },
    } as any)
    mockDeleteSubscription.mockResolvedValue(undefined)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(mockDeleteSubscription).toHaveBeenCalledWith("https://endpoint")
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.disabled", severity: "success" })
    )
  })

  it("disableNotifications: an endpoint-free subscription disables locally without deletion", async () => {
    const sub = {
      endpoint: "",
      unsubscribe: vi.fn(async () => false),
    }
    mockResolveServiceWorkerRegistration.mockResolvedValue({
      pushManager: { getSubscription: vi.fn(async () => sub) },
    } as any)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(mockDeleteSubscription).not.toHaveBeenCalled()
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.disabled", severity: "success" })
    )
  })

  it("disableNotifications: unsubscribe throws + delete throws → disabledLocal + logging (250-271)", async () => {
    mockIsPushSupported.mockReturnValue(true)
    const sub = {
      endpoint: "https://endpoint",
      unsubscribe: vi.fn(async () => {
        throw new Error("unsub fail")
      }),
    }
    mockResolveServiceWorkerRegistration.mockResolvedValue({
      pushManager: { getSubscription: vi.fn(async () => sub) },
    } as any)
    mockDeleteSubscription.mockRejectedValue(new Error("delete fail"))
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(mockLogError).toHaveBeenCalledWith("Failed to unsubscribe push", expect.anything())
    expect(mockLogWarning).toHaveBeenCalledWith(
      "Failed to delete push subscription on server",
      expect.anything()
    )
    // unsubscribed=false but endpoint truthy → disabledLocal info (263-264)
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.disabledLocal",
        severity: "info",
      })
    )
  })

  it("disableNotifications: outer error → disableFailed + logError (267-271)", async () => {
    mockIsPushSupported.mockReturnValue(true)
    mockResolveServiceWorkerRegistration.mockRejectedValue(new Error("sw boom"))
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.disableNotifications()
    })

    expect(mockLogError).toHaveBeenCalledWith("Failed to disable notifications", expect.anything())
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.disableFailed", severity: "error" })
    )
  })

  // ---- handleTopicToggle branches (lines 289-332) ----

  it("handleTopicToggle: records the choice locally without any server call while disabled", async () => {
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))

    await act(async () => {
      await result.current.handleTopicToggle("news.published")({} as any, false)
    })

    expect(result.current.topicState["news.published"]).toBe(false)
    expect(mockUpdatePushTopics).not.toHaveBeenCalled()
    expect(mockEnsurePushSubscription).not.toHaveBeenCalled()
    expect(mockSetPersistedTopics).not.toHaveBeenCalledWith(
      expect.arrayContaining(["schedule.changed"]),
      expect.anything()
    )
  })

  const enableWith = async (
    result: { current: ReturnType<typeof usePushPreferences> },
    endpoint = "https://x"
  ) => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint } as any)
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    await act(async () => {
      await result.current.enableNotifications()
    })
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))
  }

  it("handleTopicToggle: enabled success → explicit PATCH + label notification (316-328)", async () => {
    mockFetchPushTopics.mockResolvedValue(serverTopics(false))
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })
    await enableWith(result, "https://endpoint")
    await waitFor(() => expect(mockFetchPushTopics).toHaveBeenCalledTimes(2))
    onNotify.mockClear()

    await act(async () => {
      await result.current.handleTopicToggle("news.published")({} as any, false)
    })

    expect(mockUpdatePushTopics).toHaveBeenCalledWith(
      "https://endpoint",
      ALL_TOPICS.filter((topic) => topic !== "news.published")
    )
    expect(mockEnsurePushSubscription).toHaveBeenCalledOnce()
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.topicDisabled:notifications:topics.newsPublished",
        severity: "success",
      })
    )
    // The server copy is refreshed after an explicit update.
    await waitFor(() => expect(mockFetchPushTopics).toHaveBeenCalledTimes(3))

    onNotify.mockClear()
    await act(async () => {
      await result.current.handleTopicToggle("news.published")({} as any, true)
    })

    expect(mockUpdatePushTopics).toHaveBeenLastCalledWith("https://endpoint", [...ALL_TOPICS])
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.topicEnabled:notifications:topics.newsPublished",
        severity: "success",
      })
    )
  })

  it("handleTopicToggle: turning every topic off sends an explicit empty PATCH", async () => {
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await enableWith(result)

    for (const topic of ALL_TOPICS) {
      await act(async () => {
        await result.current.handleTopicToggle(topic)({} as any, false)
      })
    }

    expect(mockUpdatePushTopics).toHaveBeenLastCalledWith("https://x", [])
    expect(mockEnsurePushSubscription).toHaveBeenCalledOnce()
  })

  it("handleTopicToggle: ignores toggles while another push operation is running", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockReturnValue(never())
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))

    act(() => {
      void result.current.enableNotifications()
    })
    await waitFor(() => expect(result.current.pushBusy).toBe(true))
    await act(async () => {
      await result.current.handleTopicToggle("news.published")({} as any, false)
    })

    expect(result.current.topicState["news.published"]).toBe(true)
    expect(mockUpdatePushTopics).not.toHaveBeenCalled()
  })

  it("handleTopicToggle: enabled, PATCH throws → updateFailed + revert + logError (329-332)", async () => {
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })
    await enableWith(result)
    onNotify.mockClear()

    mockUpdatePushTopics.mockRejectedValue(new Error("patch boom"))
    await act(async () => {
      await result.current.handleTopicToggle("news.published")({} as any, false)
    })

    expect(mockLogError).toHaveBeenCalledWith("Failed to update topics", expect.anything())
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.updateFailed", severity: "error" })
    )
    expect(result.current.topicState["news.published"]).toBe(true)
    expect(result.current.pushBusy).toBe(false)
  })

  // ---- server topic hydration (ADR-041) ----

  it.each([
    ["an explicit topic list", serverTopics(true, ["news.published"]), ["news.published"]],
    ["an explicit opt-out of every topic", serverTopics(true, []), []],
    ["no stored preference (default all on)", serverTopics(false, ["news.published"]), ALL_TOPICS],
  ] as const)("hydrates topic state from %s", async (_label, response, expected) => {
    mockFetchPushTopics.mockResolvedValue(response)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.topicState).toEqual(topicStateOf(expected)))
    expect(mockSetPersistedTopics).toHaveBeenCalledWith(
      response.has_preferences ? response.topics : null,
      { userId: "7" }
    )
  })

  it("lets the server response override the cached placeholder", async () => {
    let resolveTopics!: (value: PushTopicsResponse) => void
    mockFetchPushTopics.mockReturnValue(
      new Promise<PushTopicsResponse>((resolve) => {
        resolveTopics = resolve
      })
    )
    mockGetPersistedTopics.mockReturnValue(["news.published"])
    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    expect(result.current.topicState).toEqual(topicStateOf(["news.published"]))
    expect(mockGetPersistedTopics).toHaveBeenCalledWith({ userId: "7" })

    await act(async () => {
      resolveTopics(serverTopics(false))
    })

    await waitFor(() => expect(result.current.topicState).toEqual(topicStateOf(ALL_TOPICS)))
  })

  it.each([
    ["an SSR stub", "ssr-stub", false],
    ["an encrypted-cache placeholder", "-1", false],
    ["a loading real user", 7, true],
    ["a signed-out user", null, false],
  ] as const)("does not fetch server topics for %s", async (_label, id, loading) => {
    setIdentity(id, loading)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    expect(mockFetchPushTopics).not.toHaveBeenCalled()
    expect(result.current.topicState).toEqual(topicStateOf(ALL_TOPICS))
  })

  it("does not fetch server topics when push is unsupported", async () => {
    mockIsPushSupported.mockReturnValue(false)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushSupported).toBe(false))
    expect(mockFetchPushTopics).not.toHaveBeenCalled()
  })

  it("caches the server preference under the account-scoped push-topics key", async () => {
    const response = serverTopics(true, ["events.published"])
    mockFetchPushTopics.mockResolvedValue(response)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const withClient = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client }, children)

    const { result } = renderHook(() => usePushPreferences(), { wrapper: withClient })

    await waitFor(() =>
      expect(result.current.topicState).toEqual(topicStateOf(["events.published"]))
    )
    expect(client.getQueryData(["notifications", "push-topics", "7"])).toEqual(response)
  })

  it("shows the next account's cached topics while its server copy is loading", async () => {
    mockGetPersistedTopics.mockImplementation((options?: { userId?: string }) =>
      options?.userId === "8" ? ["system.release"] : ["news.published"]
    )
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    expect(result.current.topicState).toEqual(topicStateOf(["news.published"]))

    act(() => {
      setIdentity(8)
    })

    expect(result.current.topicState).toEqual(topicStateOf(["system.release"]))
    expect(mockFetchPushTopics).toHaveBeenCalledTimes(2)
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
  })

  it("reports through the latest onNotify callback", async () => {
    mockIsPushSupported.mockReturnValue(false)
    const first = vi.fn()
    const latest = vi.fn()
    const { result, rerender } = renderHook(({ onNotify }) => usePushPreferences({ onNotify }), {
      wrapper,
      initialProps: { onNotify: first },
    })

    rerender({ onNotify: latest })
    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(latest).toHaveBeenCalledWith(expect.objectContaining({ severity: "warning" }))
    expect(first).not.toHaveBeenCalled()
  })

  it("handleTopicToggle: marks push as busy until the explicit update settles", async () => {
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await enableWith(result)
    let finish: () => void = () => undefined
    mockUpdatePushTopics.mockReturnValue(
      new Promise<undefined>((resolve) => {
        finish = () => resolve(undefined)
      })
    )

    let pending: Promise<void> = Promise.resolve()
    act(() => {
      pending = result.current.handleTopicToggle("news.published")({} as any, false)
    })
    expect(result.current.pushBusy).toBe(true)

    await act(async () => {
      finish()
      await pending
    })
    expect(result.current.pushBusy).toBe(false)
  })

  it("re-hydrates topics for a newly confirmed account", async () => {
    mockFetchPushTopics.mockResolvedValueOnce(serverTopics(true, ["news.published"]))
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.topicState).toEqual(topicStateOf(["news.published"])))

    mockFetchPushTopics.mockResolvedValueOnce(serverTopics(true, ["system.release"]))
    act(() => {
      setIdentity(8)
    })

    await waitFor(() => expect(result.current.topicState).toEqual(topicStateOf(["system.release"])))
    expect(mockSetPersistedTopics).toHaveBeenLastCalledWith(["system.release"], { userId: "8" })
  })

  // ---- permission-query effect (lines 369-402) ----

  it("permission effect: addEventListener path drives notificationPermission (369-388)", async () => {
    installNotification("default")
    let changeHandler: (() => void) | undefined
    const status: any = {
      state: "granted",
      addEventListener: vi.fn((_evt: string, h: () => void) => {
        changeHandler = h
      }),
      removeEventListener: vi.fn(),
    }
    ;(globalThis.navigator as any).permissions = {
      query: vi.fn(async () => status),
    }

    const { result, unmount } = renderHook(() => usePushPreferences(), { wrapper })

    // Initial handler() call sets permission to "granted"
    await waitFor(() => expect(result.current.notificationPermission).toBe("granted"))

    // Drive a change event with "prompt" → maps to "default" (line 376)
    status.state = "prompt"
    await act(async () => {
      changeHandler?.()
    })
    await waitFor(() => expect(result.current.notificationPermission).toBe("default"))

    unmount()
    expect(status.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function))
    expect(() => changeHandler?.()).not.toThrow()
  })

  it("permission effect: onchange fallback path (389-399)", async () => {
    installNotification("default")
    const status: any = {
      state: "denied",
      onchange: null,
      // no addEventListener → falls into the onchange branch
    }
    ;(globalThis.navigator as any).permissions = {
      query: vi.fn(async () => status),
    }

    const { result, unmount } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.notificationPermission).toBe("denied"))
    expect(typeof status.onchange).toBe("function")

    unmount()
    expect(status.onchange).toBeNull()
  })

  it("does not clear a replacement permission onchange listener during cleanup", async () => {
    const replacement = vi.fn()
    const status: any = { state: "denied", onchange: null }
    ;(globalThis.navigator as any).permissions = {
      query: vi.fn(async () => status),
    }

    const { result, unmount } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.notificationPermission).toBe("denied"))
    status.onchange = replacement

    unmount()
    expect(status.onchange).toBe(replacement)
  })

  it("ignores a rejected permission status query", async () => {
    ;(globalThis.navigator as any).permissions = {
      query: vi.fn().mockRejectedValue(new Error("permissions unavailable")),
    }

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    expect(result.current.notificationPermission).toBe("default")
  })

  // ---- detectSubscription effect error path (lines 452-454) ----

  it("detectSubscription: getExistingPushSubscription throws → logWarning detectFailed (452-454)", async () => {
    mockIsPushSupported.mockReturnValue(true)
    mockHasPushConsent.mockReturnValue(false)
    mockGetExistingPushSubscription.mockRejectedValue(new Error("detect boom"))

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() =>
      expect(mockLogWarning).toHaveBeenCalledWith(
        "notifications:messages.detectFailed",
        expect.anything()
      )
    )
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
  })

  it("detectSubscription is read-only even with consent and granted permission", async () => {
    installNotification("granted")
    mockIsPushSupported.mockReturnValue(true)
    mockHasPushConsent.mockReturnValue(true)
    mockGetPersistedTopics.mockReturnValue(["news"])
    const subscription = { endpoint: "https://detected" } as PushSubscription
    mockGetExistingPushSubscription.mockResolvedValue(subscription)

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushSubscription).toBe(subscription))
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    expect(mockEnsurePushSubscription).not.toHaveBeenCalled()
    expect(mockUpdatePushTopics).not.toHaveBeenCalled()
    expect(mockSetPushConsent).not.toHaveBeenCalled()
  })

  it("detectSubscription: keeps an existing subscription without local consent or topics", async () => {
    const subscription = { endpoint: "https://existing" } as PushSubscription
    mockHasPushConsent.mockReturnValue(false)
    mockGetPersistedTopics.mockReturnValue(undefined)
    mockGetExistingPushSubscription.mockResolvedValue(subscription)

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushSubscription).toBe(subscription))
    expect(mockSetPushConsent).not.toHaveBeenCalledWith(true)
  })

  it("detectSubscription asks only for the confirmed account's own subscription", async () => {
    setIdentity("user-7")
    mockGetExistingPushSubscription.mockResolvedValue(null)

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    expect(mockGetExistingPushSubscription).toHaveBeenLastCalledWith("user-7")
    expect(result.current.notificationsEnabled).toBe(false)
  })

  // ---- invalidatePushQueries predicate (lines 86-95) ----

  it("invalidatePushQueries predicate is exercised via enable success path (86-95)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)

    // Seed a query client with matching + non-matching keys so the predicate runs both branches.
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })
    client.setQueryData(["users", "me"], { id: 7 })
    client.setQueryData(["notifications", "list"], [])
    client.setQueryData(["unrelated", "thing"], 1)
    const invalidateSpy = vi.spyOn(client, "invalidateQueries")
    const localWrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client }, children)

    const { result } = renderHook(() => usePushPreferences(), { wrapper: localWrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

    expect(invalidateSpy).toHaveBeenCalled()
    const predicate = invalidateSpy.mock.calls[0]![0]!.predicate as (q: any) => boolean
    expect(predicate({ queryKey: ["users", "me"] })).toBe(true)
    expect(predicate({ queryKey: ["notifications", "list"] })).toBe(true)
    expect(predicate({ queryKey: ["notifications", "push-topics", "7"] })).toBe(true)
    expect(predicate({ queryKey: ["unrelated", "thing"] })).toBe(false)
    expect(predicate({ queryKey: "not-an-array" })).toBe(false)
  })

  it("supports an anonymous user and reports when every topic is disabled", async () => {
    setIdentity(null)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    for (const topic of NOTIFICATION_TOPIC_KEYS) {
      await act(async () => {
        await result.current.handleTopicToggle(topic)({} as any, false)
      })
    }

    expect(result.current.selectedTopicsDescription).toBe("notifications:messages.noTopics")
  })

  it("ignores a null persisted-topic payload", async () => {
    mockGetPersistedTopics.mockReturnValue(null)

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    expect(result.current.topicState).toEqual(
      Object.fromEntries(NOTIFICATION_TOPIC_KEYS.map((topic) => [topic, true]))
    )
  })

  it("filters empty persisted topic values", async () => {
    mockGetPersistedTopics.mockReturnValue(["", "news"])

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    expect(result.current.topicState).toEqual({
      "news.published": true,
      "schedule.changed": false,
      "events.published": false,
      "chat.message.created": false,
      "system.release": false,
    })
  })

  it("ignores normalized topic names outside the supported set", async () => {
    mockGetPersistedTopics.mockReturnValue(["unknown-topic"])

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    expect(result.current.topicState).toEqual({
      "news.published": false,
      "schedule.changed": false,
      "events.published": false,
      "chat.message.created": false,
      "system.release": false,
    })
  })

  it("does not update permission state after the hook unmounts", async () => {
    let resolveQuery: ((status: PermissionStatus) => void) | undefined
    const pendingQuery = new Promise<PermissionStatus>((resolve) => {
      resolveQuery = resolve
    })
    const status = {
      state: "granted",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }
    ;(globalThis.navigator as any).permissions = {
      query: vi.fn(() => pendingQuery),
    }

    const { unmount } = renderHook(() => usePushPreferences(), { wrapper })
    unmount()
    resolveQuery?.(status as unknown as PermissionStatus)
    await act(async () => {
      await pendingQuery
    })

    expect(status.addEventListener).not.toHaveBeenCalled()
  })

  it("does not update subscription state after an async detection resolves post-unmount", async () => {
    let resolveSubscription: ((value: PushSubscription | null) => void) | undefined
    const pendingSubscription = new Promise<PushSubscription | null>((resolve) => {
      resolveSubscription = resolve
    })
    mockGetExistingPushSubscription.mockReturnValue(pendingSubscription)

    const { unmount } = renderHook(() => usePushPreferences(), { wrapper })
    unmount()
    resolveSubscription?.(null)
    await act(async () => {
      await pendingSubscription
    })

    expect(mockGetExistingPushSubscription).toHaveBeenCalled()
  })

  it("does not log a late subscription detection failure after unmount", async () => {
    let rejectSubscription: ((reason: Error) => void) | undefined
    const pendingSubscription = new Promise<PushSubscription | null>((_resolve, reject) => {
      rejectSubscription = reject
    })
    mockGetExistingPushSubscription.mockReturnValue(pendingSubscription)

    const { unmount } = renderHook(() => usePushPreferences(), { wrapper })
    unmount()
    rejectSubscription?.(new Error("late detection failure"))
    await act(async () => {
      await pendingSubscription.catch(() => undefined)
    })

    expect(mockLogWarning).not.toHaveBeenCalledWith(
      "notifications:messages.detectFailed",
      expect.anything()
    )
  })

  it("swallows permission listener cleanup failures", async () => {
    const status = {
      state: "granted",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(() => {
        throw new Error("listener already gone")
      }),
    }
    ;(globalThis.navigator as any).permissions = {
      query: vi.fn(async () => status),
    }

    const { result, unmount } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.notificationPermission).toBe("granted"))
    expect(() => unmount()).not.toThrow()
    expect(status.removeEventListener).toHaveBeenCalled()
  })
})
