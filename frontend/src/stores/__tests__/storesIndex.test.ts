import { describe, expect, it } from "vitest"
import {
  useAuthStore,
  useAuthUser,
  useAuthLoading,
  useAuthPendingMfa,
  useAuthOperation,
  useAuthActions,
  useNotificationStore,
  useScheduleUIStore,
  useAppShellStore,
  useNotificationTopics,
  useNotificationPermission,
  useToasts,
  useNotificationActions,
  useWeekOffset,
  useViewMode,
  useHiddenWeekdays,
  useScheduleDisplayPreferences,
  useScheduleUIActions,
  useSidebarCollapsed,
  useMobileDrawerOpen,
  useThemeMode,
  useAppShellActions,
} from "../index"

describe("Stores Index re-exports", () => {
  it("successfully exports all stores and selectors", () => {
    expect(useAuthStore).toBeDefined()
    expect(useAuthUser).toBeDefined()
    expect(useAuthLoading).toBeDefined()
    expect(useAuthPendingMfa).toBeDefined()
    expect(useAuthOperation).toBeDefined()
    expect(useAuthActions).toBeDefined()
    expect(useNotificationStore).toBeDefined()
    expect(useScheduleUIStore).toBeDefined()
    expect(useAppShellStore).toBeDefined()
    expect(useNotificationTopics).toBeDefined()
    expect(useNotificationPermission).toBeDefined()
    expect(useToasts).toBeDefined()
    expect(useNotificationActions).toBeDefined()
    expect(useWeekOffset).toBeDefined()
    expect(useViewMode).toBeDefined()
    expect(useHiddenWeekdays).toBeDefined()
    expect(useScheduleDisplayPreferences).toBeDefined()
    expect(useScheduleUIActions).toBeDefined()
    expect(useSidebarCollapsed).toBeDefined()
    expect(useMobileDrawerOpen).toBeDefined()
    expect(useThemeMode).toBeDefined()
    expect(useAppShellActions).toBeDefined()
  })
})
