/**
 * Features Index
 *
 * Central export point for all feature modules.
 * Import from here for clean, organized access to feature functionality.
 *
 * @example
 * ```ts
 * import { useAuth, EventCard, useScheduleData } from '@/features'
 * ```
 */

// Auth
export * from "./auth"

// Events
export * from "./events"

// News
export * from "./news"

// Schedule
export * from "./schedule"

// Messenger
export * from "./messenger"

// Settings
export * from "./settings"

// Dashboard
export * from "./dashboard"

// Admin (exported separately to avoid conflicts)
export * as admin from "./admin"




