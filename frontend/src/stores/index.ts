/**
 * Zustand Stores Index
 *
 * Re-exports all stores for clean imports.
 *
 * @example
 * ```ts
 * import { useNotificationStore, useScheduleUIStore, useAppShellStore } from '@/stores'
 * ```
 */

// Store exports
export {
  useAuthStore,
  useAuthUser,
  useAuthLoading,
  useAuthPendingMfa,
  useAuthOperation,
  useAuthActions,
} from "./useAuthStore"
export { useNotificationStore } from "./notificationStore"
export { useScheduleUIStore } from "./scheduleUIStore"
export { useAppShellStore } from "./appShellStore"

// Notification store selectors
export {
  useNotificationTopics,
  useNotificationPermission,
  useToasts,
  useNotificationActions,
} from "./notificationStore"

// Schedule UI store selectors
export {
  useWeekOffset,
  useViewMode,
  useHiddenWeekdays,
  useScheduleDisplayPreferences,
  useScheduleUIActions,
} from "./scheduleUIStore"

// App shell store selectors
export {
  useSidebarCollapsed,
  useMobileDrawerOpen,
  useThemeMode,
  useAppShellActions,
} from "./appShellStore"

// Types
export type {
  NotificationTopicKey,
  NotificationPermissionState,
  Toast,
  ToastSeverity,
  ScheduleViewMode,
  ThemeMode,
} from "./types"
