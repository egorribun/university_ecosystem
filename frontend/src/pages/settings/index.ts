// Settings Page - Modular Architecture
// The original 2277-line Settings.tsx has been decomposed into:
// - sections/: UI sections for each tab
// - hooks/: Reusable logic hooks

export {
  AppearanceSection,
  NotificationsSection,
  SpotifySection,
  ProfileSection,
  SessionsSection,
  PasswordSection,
} from "./sections"
export { useAvatarUpload, useCoverUpload, useEmailMfa } from "./hooks"
export type { SnackbarState, SetSnackbar, SettingsSectionProps } from "./types"
