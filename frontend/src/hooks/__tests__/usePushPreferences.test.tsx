import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import type { ReactNode } from "react"
import { createElement } from "react"

// ---- Module mocks (NEVER hit MSW for /api/ paths) ----
const mockDeleteSubscription = vi.fn(async (..._a: unknown[]) => undefined)
vi.mock("@/api/notifications", () => ({
  deleteSubscription: (...args: unknown[]) => mockDeleteSubscription(...args),
}))

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
  getExistingPushSubscription: (...args: unknown[]) => mockGetExistingPushSubscription(...args),
  hasPushConsent: () => mockHasPushConsent(),
  setPersistedTopics: (...args: unknown[]) => mockSetPersistedTopics(...args),
}))

const mockUseAuth = vi.fn(() => ({ user: { id: 7 } }) as any)
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
  currentUserQueryKey: ["users", "me"] as const,
}))

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
  ;(globalThis as any).Notification = { permission }
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
    mockUseAuth.mockReturnValue({ user: { id: 7 } } as any)
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

    // All four default topics are selected → description is a join of labels (lines 120-126)
    expect(result.current.selectedTopicsDescription).toContain("notifications:topics.schedule")
    expect(result.current.permissionText).toBe("notifications:permission.default")
    expect(result.current.safariGuideUrl).toContain("support.apple.com")

    // detectSubscription effect resolves → pushInitializing flips false (lines 410-463 happy path)
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
  })

  // ---- enableNotifications branches (lines 150-216) ----

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
    installNotification("default")
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

  it("enableNotifications: subscription present but permission not granted → enableInSettings (191-199)", async () => {
    installNotification("default")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
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
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    mockGetPersistedTopics.mockReturnValue(["news", "events"])
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })

    await act(async () => {
      await result.current.enableNotifications()
    })

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

  it("handleTopicToggle: persists + early-returns when notifications disabled", async () => {
    // notificationsEnabled is false (no subscription) → returns after persisting (line 287)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))

    await act(async () => {
      await result.current.handleTopicToggle("news")({} as any, false)
    })

    expect(mockSetPersistedTopics).toHaveBeenCalled()
    expect(result.current.topicState.news).toBe(false)
  })

  it("handleTopicToggle: unsupported reverts topic state (288-291)", async () => {
    // First enable notifications so notificationsEnabled becomes true, then make push unsupported.
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    await act(async () => {
      await result.current.enableNotifications()
    })
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))

    mockIsPushSupported.mockReturnValue(false)
    await act(async () => {
      await result.current.handleTopicToggle("news")({} as any, false)
    })

    // state reverted to previous (true) after unsupported guard
    await waitFor(() => expect(result.current.topicState.news).toBe(true))
  })

  it("handleTopicToggle: enabled, no SW → workerUnavailable + revert (296-300)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    await act(async () => {
      await result.current.enableNotifications()
    })
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))
    onNotify.mockClear()

    mockResolveServiceWorkerRegistration.mockResolvedValue(null)
    await act(async () => {
      await result.current.handleTopicToggle("news")({} as any, false)
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.workerUnavailable" })
    )
  })

  it("handleTopicToggle: enabled, subscription null → permission hint + revert (306-315)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    await act(async () => {
      await result.current.enableNotifications()
    })
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))
    onNotify.mockClear()

    mockEnsurePushSubscription.mockResolvedValue(null)
    await act(async () => {
      await result.current.handleTopicToggle("news")({} as any, false)
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.subscriptionPermissionHint",
        severity: "warning",
      })
    )
  })

  it("handleTopicToggle: enabled success → topicDisabled label notification (316-328)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    mockGetPersistedTopics.mockReturnValue(["schedule", "events", "system"])
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    await act(async () => {
      await result.current.enableNotifications()
    })
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))
    onNotify.mockClear()

    await act(async () => {
      await result.current.handleTopicToggle("news")({} as any, false)
    })

    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "notifications:messages.topicDisabled:notifications:topics.news",
        severity: "success",
      })
    )
  })

  it("handleTopicToggle: enabled, ensure throws → updateFailed + revert + logError (329-332)", async () => {
    installNotification("granted")
    mockResolveServiceWorkerRegistration.mockResolvedValue({} as any)
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://x" } as any)
    const onNotify = vi.fn()
    const { result } = renderHook(() => usePushPreferences({ onNotify }), { wrapper })
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    await act(async () => {
      await result.current.enableNotifications()
    })
    await waitFor(() => expect(result.current.notificationsEnabled).toBe(true))
    onNotify.mockClear()

    mockEnsurePushSubscription.mockRejectedValue(new Error("ensure boom"))
    await act(async () => {
      await result.current.handleTopicToggle("news")({} as any, false)
    })

    expect(mockLogError).toHaveBeenCalledWith("Failed to update topics", expect.anything())
    expect(onNotify).toHaveBeenCalledWith(
      expect.objectContaining({ text: "notifications:messages.updateFailed", severity: "error" })
    )
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

  it("detectSubscription: consented + granted → ensurePushSubscription path (428-450)", async () => {
    installNotification("granted")
    mockIsPushSupported.mockReturnValue(true)
    mockHasPushConsent.mockReturnValue(true)
    mockGetPersistedTopics.mockReturnValue(["news"])
    mockEnsurePushSubscription.mockResolvedValue({ endpoint: "https://detected" } as any)

    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushSubscription).not.toBeNull())
    expect(mockSetPushConsent).toHaveBeenCalledWith(true)
    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
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
    expect(predicate({ queryKey: ["unrelated", "thing"] })).toBe(false)
    expect(predicate({ queryKey: "not-an-array" })).toBe(false)
  })

  it("supports an anonymous user and reports when every topic is disabled", async () => {
    mockUseAuth.mockReturnValue({ user: null } as any)
    const { result } = renderHook(() => usePushPreferences(), { wrapper })

    await waitFor(() => expect(result.current.pushInitializing).toBe(false))
    for (const topic of NOTIFICATION_TOPIC_KEYS) {
      await act(async () => {
        await result.current.handleTopicToggle(topic)({} as any, false)
      })
    }

    expect(result.current.selectedTopicsDescription).toBe("notifications:messages.noTopics")
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
