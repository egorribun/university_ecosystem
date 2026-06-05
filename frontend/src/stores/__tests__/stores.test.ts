/**
 * Unit tests for Zustand stores.
 */

import { describe, it, expect, beforeEach, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import type { PendingMfaState, UserState } from "@/types/Auth"

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
    clear: vi.fn(() => {
      store = {}
    }),
  }
})()

Object.defineProperty(window, "localStorage", { value: localStorageMock })

describe("notificationStore", () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.resetModules()
  })

  it("should have default topic preferences", async () => {
    const { useNotificationStore } = await import("../notificationStore")
    const state = useNotificationStore.getState()

    expect(state.topics.schedule).toBe(true)
    expect(state.topics.news).toBe(true)
    expect(state.topics.events).toBe(true)
    expect(state.topics.system).toBe(true)
  })

  it("should update topic preference", async () => {
    const { useNotificationStore } = await import("../notificationStore")

    act(() => {
      useNotificationStore.getState().setTopic("schedule", false)
    })

    expect(useNotificationStore.getState().topics.schedule).toBe(false)
  })

  it("should add and remove toasts", async () => {
    const { useNotificationStore } = await import("../notificationStore")

    act(() => {
      useNotificationStore.getState().addToast("Test message", "success")
    })

    const toasts = useNotificationStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0]!.message).toBe("Test message")
    expect(toasts[0]!.severity).toBe("success")

    const toastId = toasts[0]!.id

    act(() => {
      useNotificationStore.getState().removeToast(toastId)
    })

    expect(useNotificationStore.getState().toasts).toHaveLength(0)
  })

  it("should update permission state", async () => {
    const { useNotificationStore } = await import("../notificationStore")

    act(() => {
      useNotificationStore.getState().setPermission("granted")
    })

    expect(useNotificationStore.getState().permission).toBe("granted")
  })

  it("should reset topics to defaults", async () => {
    const { useNotificationStore } = await import("../notificationStore")

    act(() => {
      useNotificationStore.getState().setTopic("schedule", false)
      useNotificationStore.getState().setTopic("news", false)
    })

    expect(useNotificationStore.getState().topics.schedule).toBe(false)

    act(() => {
      useNotificationStore.getState().resetTopics()
    })

    expect(useNotificationStore.getState().topics.schedule).toBe(true)
    expect(useNotificationStore.getState().topics.news).toBe(true)
  })
})

describe("scheduleUIStore", () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.resetModules()
  })

  it("should have default state", async () => {
    const { useScheduleUIStore } = await import("../scheduleUIStore")
    const state = useScheduleUIStore.getState()

    expect(state.weekOffset).toBe(0)
    expect(state.viewMode).toBe("week")
    expect(state.hiddenWeekdays).toEqual([])
    expect(state.showPastLessons).toBe(true)
    expect(state.compactMode).toBe(false)
  })

  it("should navigate weeks", async () => {
    const { useScheduleUIStore } = await import("../scheduleUIStore")

    act(() => {
      useScheduleUIStore.getState().nextWeek()
    })
    expect(useScheduleUIStore.getState().weekOffset).toBe(1)

    act(() => {
      useScheduleUIStore.getState().nextWeek()
    })
    expect(useScheduleUIStore.getState().weekOffset).toBe(2)

    act(() => {
      useScheduleUIStore.getState().previousWeek()
    })
    expect(useScheduleUIStore.getState().weekOffset).toBe(1)

    act(() => {
      useScheduleUIStore.getState().goToCurrentWeek()
    })
    expect(useScheduleUIStore.getState().weekOffset).toBe(0)
  })

  it("should toggle weekday visibility", async () => {
    const { useScheduleUIStore } = await import("../scheduleUIStore")

    act(() => {
      useScheduleUIStore.getState().toggleWeekday(0)
    })
    expect(useScheduleUIStore.getState().hiddenWeekdays).toContain(0)

    act(() => {
      useScheduleUIStore.getState().toggleWeekday(0)
    })
    expect(useScheduleUIStore.getState().hiddenWeekdays).not.toContain(0)
  })

  it("should change view mode", async () => {
    const { useScheduleUIStore } = await import("../scheduleUIStore")

    act(() => {
      useScheduleUIStore.getState().setViewMode("day")
    })
    expect(useScheduleUIStore.getState().viewMode).toBe("day")

    act(() => {
      useScheduleUIStore.getState().setViewMode("list")
    })
    expect(useScheduleUIStore.getState().viewMode).toBe("list")
  })

  it("should toggle display preferences", async () => {
    const { useScheduleUIStore } = await import("../scheduleUIStore")

    act(() => {
      useScheduleUIStore.getState().togglePastLessons()
    })
    expect(useScheduleUIStore.getState().showPastLessons).toBe(false)

    act(() => {
      useScheduleUIStore.getState().toggleCompactMode()
    })
    expect(useScheduleUIStore.getState().compactMode).toBe(true)
  })
})

describe("appShellStore", () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.resetModules()
  })

  it("should have default state", async () => {
    const { useAppShellStore } = await import("../appShellStore")
    const state = useAppShellStore.getState()

    expect(state.sidebarCollapsed).toBe(false)
    expect(state.mobileDrawerOpen).toBe(false)
    expect(state.themeMode).toBe("system")
  })

  it("should toggle sidebar", async () => {
    const { useAppShellStore } = await import("../appShellStore")

    act(() => {
      useAppShellStore.getState().toggleSidebar()
    })
    expect(useAppShellStore.getState().sidebarCollapsed).toBe(true)

    act(() => {
      useAppShellStore.getState().toggleSidebar()
    })
    expect(useAppShellStore.getState().sidebarCollapsed).toBe(false)
  })

  it("should control mobile drawer", async () => {
    const { useAppShellStore } = await import("../appShellStore")

    act(() => {
      useAppShellStore.getState().openMobileDrawer()
    })
    expect(useAppShellStore.getState().mobileDrawerOpen).toBe(true)

    act(() => {
      useAppShellStore.getState().closeMobileDrawer()
    })
    expect(useAppShellStore.getState().mobileDrawerOpen).toBe(false)
  })

  it("should cycle theme modes", async () => {
    const { useAppShellStore } = await import("../appShellStore")

    expect(useAppShellStore.getState().themeMode).toBe("system")

    act(() => {
      useAppShellStore.getState().cycleThemeMode()
    })
    expect(useAppShellStore.getState().themeMode).toBe("light")

    act(() => {
      useAppShellStore.getState().cycleThemeMode()
    })
    expect(useAppShellStore.getState().themeMode).toBe("dark")

    act(() => {
      useAppShellStore.getState().cycleThemeMode()
    })
    expect(useAppShellStore.getState().themeMode).toBe("system")
  })

  it("should set theme mode directly", async () => {
    const { useAppShellStore } = await import("../appShellStore")

    act(() => {
      useAppShellStore.getState().setThemeMode("dark")
    })
    expect(useAppShellStore.getState().themeMode).toBe("dark")
  })
})

describe("useAuthStore", () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it("should have default state", async () => {
    const { useAuthStore } = await import("../useAuthStore")
    const state = useAuthStore.getState()

    expect(state.user).toBeNull()
    expect(state.loading).toBe(true)
    expect(state.pendingMfa).toBeNull()
    expect(state.authOperation).toBe(false)
  })

  it("should update user state with direct value or updater function", async () => {
    const { useAuthStore } = await import("../useAuthStore")

    const mockUser = {
      id: "user-123",
      email: "user@example.com",
      name: "User",
    } as unknown as UserState

    act(() => {
      useAuthStore.getState().setUser(mockUser)
    })
    expect(useAuthStore.getState().user).toEqual(mockUser)

    act(() => {
      useAuthStore
        .getState()
        .setUser((prev) => ({ ...(prev as object), name: "Updated Name" }) as unknown as UserState)
    })
    expect(useAuthStore.getState().user).toEqual({ ...mockUser, name: "Updated Name" })
  })

  it("should update loading state", async () => {
    const { useAuthStore } = await import("../useAuthStore")

    act(() => {
      useAuthStore.getState().setLoading(false)
    })
    expect(useAuthStore.getState().loading).toBe(false)
  })

  it("should update pending MFA state", async () => {
    const { useAuthStore } = await import("../useAuthStore")

    const mockMfa = { ticket: "mfa-ticket", methods: [] } as unknown as PendingMfaState

    act(() => {
      useAuthStore.getState().setPendingMfa(mockMfa)
    })
    expect(useAuthStore.getState().pendingMfa).toEqual(mockMfa)
  })

  it("should update auth operation state", async () => {
    const { useAuthStore } = await import("../useAuthStore")

    act(() => {
      useAuthStore.getState().setAuthOperation(true)
    })
    expect(useAuthStore.getState().authOperation).toBe(true)
  })
})

describe("store selector hooks and remaining actions", () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.resetModules()
  })

  it("appShell: setSidebarCollapsed and toggleMobileDrawer", async () => {
    const { useAppShellStore } = await import("../appShellStore")

    act(() => {
      useAppShellStore.getState().setSidebarCollapsed(true)
    })
    expect(useAppShellStore.getState().sidebarCollapsed).toBe(true)

    act(() => {
      useAppShellStore.getState().toggleMobileDrawer()
    })
    expect(useAppShellStore.getState().mobileDrawerOpen).toBe(true)

    act(() => {
      useAppShellStore.getState().toggleMobileDrawer()
    })
    expect(useAppShellStore.getState().mobileDrawerOpen).toBe(false)
  })

  it("appShell: selector hooks reflect store state", async () => {
    const mod = await import("../appShellStore")

    expect(renderHook(() => mod.useSidebarCollapsed()).result.current).toBe(false)
    expect(renderHook(() => mod.useMobileDrawerOpen()).result.current).toBe(false)
    expect(renderHook(() => mod.useThemeMode()).result.current).toBe("system")

    const { result } = renderHook(() => mod.useAppShellActions())
    expect(typeof result.current.toggleSidebar).toBe("function")
    act(() => {
      result.current.setThemeMode("dark")
    })
    expect(mod.useAppShellStore.getState().themeMode).toBe("dark")
  })

  it("notification: setAllTopics, clearToasts, and addToast defaults", async () => {
    const { useNotificationStore } = await import("../notificationStore")

    act(() => {
      useNotificationStore.getState().setAllTopics({
        schedule: false,
        news: false,
        events: false,
        system: false,
      })
    })
    expect(useNotificationStore.getState().topics.schedule).toBe(false)

    act(() => {
      useNotificationStore.getState().addToast("default toast")
    })
    const toast = useNotificationStore.getState().toasts[0]!
    expect(toast.severity).toBe("info") // default severity
    expect(toast.duration).toBe(5000) // default duration

    act(() => {
      useNotificationStore.getState().addToast("second")
      useNotificationStore.getState().clearToasts()
    })
    expect(useNotificationStore.getState().toasts).toHaveLength(0)
  })

  it("notification: selector hooks reflect store state", async () => {
    const mod = await import("../notificationStore")

    expect(renderHook(() => mod.useNotificationTopics()).result.current.schedule).toBe(true)
    expect(renderHook(() => mod.useNotificationPermission()).result.current).toBe("default")
    expect(renderHook(() => mod.useToasts()).result.current).toEqual([])

    const { result } = renderHook(() => mod.useNotificationActions())
    expect(typeof result.current.addToast).toBe("function")
  })

  it("scheduleUI: setWeekOffset, setHiddenWeekdays, resetPreferences", async () => {
    const { useScheduleUIStore } = await import("../scheduleUIStore")

    act(() => {
      useScheduleUIStore.getState().setWeekOffset(5)
      useScheduleUIStore.getState().setHiddenWeekdays([1, 2])
    })
    expect(useScheduleUIStore.getState().weekOffset).toBe(5)
    expect(useScheduleUIStore.getState().hiddenWeekdays).toEqual([1, 2])

    act(() => {
      useScheduleUIStore.getState().resetPreferences()
    })
    expect(useScheduleUIStore.getState().weekOffset).toBe(0)
    expect(useScheduleUIStore.getState().hiddenWeekdays).toEqual([])
  })

  it("scheduleUI: selector hooks reflect store state", async () => {
    const mod = await import("../scheduleUIStore")

    expect(renderHook(() => mod.useWeekOffset()).result.current).toBe(0)
    expect(renderHook(() => mod.useViewMode()).result.current).toBe("week")
    expect(renderHook(() => mod.useHiddenWeekdays()).result.current).toEqual([])
    expect(
      renderHook(() => mod.useScheduleDisplayPreferences()).result.current.showPastLessons
    ).toBe(true)

    const { result } = renderHook(() => mod.useScheduleUIActions())
    expect(typeof result.current.nextWeek).toBe("function")
  })

  it("auth: selector hooks reflect store state", async () => {
    const mod = await import("../useAuthStore")

    expect(renderHook(() => mod.useAuthUser()).result.current).toBeNull()
    expect(renderHook(() => mod.useAuthLoading()).result.current).toBe(true)
    expect(renderHook(() => mod.useAuthPendingMfa()).result.current).toBeNull()
    expect(renderHook(() => mod.useAuthOperation()).result.current).toBe(false)

    const { result } = renderHook(() => mod.useAuthActions())
    expect(typeof result.current.setUser).toBe("function")
    act(() => {
      result.current.setLoading(false)
    })
    expect(mod.useAuthStore.getState().loading).toBe(false)
  })
})
