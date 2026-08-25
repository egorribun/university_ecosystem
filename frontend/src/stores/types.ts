/**
 * Shared types for Zustand stores.
 */

/** Notification topic keys */
export type { NotificationTopic as NotificationTopicKey } from "@/notifications/contract"

/** Toast severity levels */
export type ToastSeverity = "success" | "info" | "warning" | "error"

/** Toast notification */
export interface Toast {
  id: string
  message: string
  severity: ToastSeverity
  duration?: number
}

/** Schedule view modes */
export type ScheduleViewMode = "week" | "day" | "list"

/** Theme modes */
export type ThemeMode = "light" | "dark" | "system"

/** Notification permission states */
export type NotificationPermissionState = "default" | "granted" | "denied" | "unsupported"
