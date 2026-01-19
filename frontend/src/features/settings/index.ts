/**
 * Settings Feature
 *
 * Handles user settings: profile, notifications, security, preferences.
 */

// Re-export hooks from existing locations
export { usePushPreferences } from "@/hooks/usePushPreferences"

// Stores
export {
  useNotificationStore,
  useNotificationTopics,
  useNotificationActions,
  useAppShellStore,
  useThemeMode,
} from "@/stores"

// Components will be added as migration progresses
// export { SettingsSection } from './components/SettingsSection'
// export { NotificationSettings } from './components/NotificationSettings'
