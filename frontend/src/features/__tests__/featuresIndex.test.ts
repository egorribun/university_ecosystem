import { describe, expect, it } from "vitest"
import {
  useScheduleData,
  useDashboardSchedule,
  useClassReminders,
  useScheduleUIStore,
  useWeekOffset,
  useViewMode,
  ScheduleDesktopTable,
  ScheduleMobileView,
  ScheduleListView,
  LessonCard,
  ScheduleSettingsPanel,
  usePushPreferences,
  useNotificationStore,
  useNotificationTopics,
  useNotificationActions,
  useAppShellStore,
  useThemeMode,
  AuthContext,
  AuthProvider,
  useAuth,
  DashboardStories,
  WeatherWidget,
  useDashboardStories,
  useWeather,
  useNowPlaying,
  admin
} from "../index"

describe("Features Index re-exports", () => {
  it("exports schedule items", () => {
    expect(useScheduleData).toBeDefined()
    expect(useDashboardSchedule).toBeDefined()
    expect(useClassReminders).toBeDefined()
    expect(useScheduleUIStore).toBeDefined()
    expect(useWeekOffset).toBeDefined()
    expect(useViewMode).toBeDefined()
    expect(ScheduleSettingsPanel).toBeDefined()
  })

  it("exports settings items", () => {
    expect(usePushPreferences).toBeDefined()
    expect(useNotificationStore).toBeDefined()
    expect(useNotificationTopics).toBeDefined()
    expect(useNotificationActions).toBeDefined()
    expect(useAppShellStore).toBeDefined()
    expect(useThemeMode).toBeDefined()
  })

  it("exports auth items", () => {
    expect(AuthContext).toBeDefined()
    expect(AuthProvider).toBeDefined()
    expect(useAuth).toBeDefined()
  })

  it("exports dashboard items", () => {
    expect(DashboardStories).toBeDefined()
    expect(WeatherWidget).toBeDefined()
    expect(useDashboardStories).toBeDefined()
    expect(useWeather).toBeDefined()
    expect(useNowPlaying).toBeDefined()
  })

  it("exports admin namespace", () => {
    expect(admin).toBeDefined()
  })
})
