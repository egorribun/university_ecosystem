/**
 * Notification Store
 *
 * Manages notification preferences, permission state, and toast queue.
 * Persists topic preferences to localStorage.
 */

import { create } from "zustand"
import { devtools, persist } from "zustand/middleware"
import { useShallow } from "zustand/react/shallow"

import type {
  NotificationTopicKey,
  NotificationPermissionState,
  Toast,
  ToastSeverity,
} from "./types"

/** Default topic preferences - all enabled */
const DEFAULT_TOPICS: Record<NotificationTopicKey, boolean> = {
  schedule: true,
  news: true,
  events: true,
  system: true,
}

interface NotificationState {
  /** Topic enable/disable preferences */
  topics: Record<NotificationTopicKey, boolean>

  /** Browser notification permission state */
  permission: NotificationPermissionState

  /** Active toast notifications */
  toasts: Toast[]

  /** Set a specific topic preference */
  setTopic: (key: NotificationTopicKey, enabled: boolean) => void

  /** Set all topic preferences at once */
  setAllTopics: (topics: Record<NotificationTopicKey, boolean>) => void

  /** Update browser permission state */
  setPermission: (permission: NotificationPermissionState) => void

  /** Add a toast notification */
  addToast: (message: string, severity?: ToastSeverity, duration?: number) => void

  /** Remove a toast by ID */
  removeToast: (id: string) => void

  /** Clear all toasts */
  clearToasts: () => void

  /** Reset topics to defaults */
  resetTopics: () => void
}

/** Generate unique toast ID */
const generateToastId = (): string => crypto.randomUUID()

export const useNotificationStore = create<NotificationState>()(
  devtools(
    persist(
      (set) => ({
        topics: { ...DEFAULT_TOPICS },
        permission: "default",
        toasts: [],

        setTopic: (key, enabled) =>
          set(
            (state) => ({
              topics: { ...state.topics, [key]: enabled },
            }),
            false,
            "setTopic"
          ),

        setAllTopics: (topics) => set({ topics: { ...topics } }, false, "setAllTopics"),

        setPermission: (permission) => set({ permission }, false, "setPermission"),

        addToast: (message, severity = "info", duration = 5000) =>
          set(
            (state) => ({
              toasts: [
                ...state.toasts,
                {
                  id: generateToastId(),
                  message,
                  severity,
                  duration,
                },
              ],
            }),
            false,
            "addToast"
          ),

        removeToast: (id) =>
          set(
            (state) => ({
              toasts: state.toasts.filter((toast) => toast.id !== id),
            }),
            false,
            "removeToast"
          ),

        clearToasts: () => set({ toasts: [] }, false, "clearToasts"),

        resetTopics: () => set({ topics: { ...DEFAULT_TOPICS } }, false, "resetTopics"),
      }),
      {
        name: "notification-preferences",
        partialize: (state) => ({
          topics: state.topics,
        }),
      }
    ),
    { name: "NotificationStore" }
  )
)

/** Selector hooks for optimized re-renders */
export const useNotificationTopics = () => useNotificationStore((state) => state.topics)

export const useNotificationPermission = () => useNotificationStore((state) => state.permission)

export const useToasts = () => useNotificationStore((state) => state.toasts)

const notificationActionsSelector = (state: NotificationState) => ({
  setTopic: state.setTopic,
  setAllTopics: state.setAllTopics,
  setPermission: state.setPermission,
  addToast: state.addToast,
  removeToast: state.removeToast,
  clearToasts: state.clearToasts,
  resetTopics: state.resetTopics,
})

export const useNotificationActions = () =>
  useNotificationStore(useShallow(notificationActionsSelector))
