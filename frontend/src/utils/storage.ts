import { logWarning } from "@/app/logger"

/**
 * Storage Utility
 *
 * Provides a type-safe wrapper around localStorage with JSON serialization,
 * error handling, and SSR safety.
 */

export const IS_BROWSER = typeof window !== "undefined"

export type StorageValue<T> = T | null

export class StorageItem<T> {
  constructor(
    private key: string,
    private fallback: T | null = null
  ) {}

  /**
   * Reads the value from localStorage.
   * Returns the parsed value or fallback if missing/invalid.
   */
  get(): StorageValue<T> {
    if (!IS_BROWSER) return this.fallback
    try {
      const raw = window.localStorage.getItem(this.key)
      if (raw === null) return this.fallback
      return JSON.parse(raw) as T
    } catch (error) {
      logWarning(`[Storage] Failed to parse key "${this.key}":`, { error })
      return this.fallback
    }
  }

  /**
   * Writes the value to localStorage.
   * Returns true on success, false if the write failed (e.g. QuotaExceededError).
   * PERF-04 (audit 2026-03-15 Wave 7): dispatches StorageEvent with newValue=null
   * on QuotaExceededError so listeners (ThemeContext, LanguageContext) know the
   * write did not succeed rather than silently treating it as successful.
   */
  set(value: T): boolean {
    if (!IS_BROWSER) return false
    try {
      const serialized = JSON.stringify(value)
      window.localStorage.setItem(this.key, serialized)
      // Manually dispatch storage event for same-tab synchronization
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: this.key,
          newValue: serialized,
          url: window.location.href,
        })
      )
      return true
    } catch (error) {
      logWarning(`[Storage] Failed to set key "${this.key}":`, { error })
      if (error instanceof DOMException && error.name === "QuotaExceededError") {
        // Notify listeners that the write failed — null newValue signals failure.
        window.dispatchEvent(
          new StorageEvent("storage", {
            key: this.key,
            newValue: null,
            url: window.location.href,
          })
        )
      }
      return false
    }
  }

  /**
   * Removes the item from localStorage.
   */
  remove(): void {
    if (!IS_BROWSER) return
    try {
      window.localStorage.removeItem(this.key)
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: this.key,
          newValue: null,
          url: window.location.href,
        })
      )
    } catch (error) {
      logWarning(`[Storage] Failed to remove key "${this.key}":`, { error })
    }
  }

  /**
   * Check if the key exists in localStorage.
   */
  exists(): boolean {
    if (!IS_BROWSER) return false
    return window.localStorage.getItem(this.key) !== null
  }
}

// Pre-defined storage keys for non-React contexts
export const pushConsentStorage = new StorageItem<"granted" | "denied">("push-notification-consent")
// TD-14-07: Only non-PII fields may be stored here.
// NEVER add: email, phone, role, permissions, address.
// See: OWASP WSTG-SESS-09 — sensitive data in localStorage.
// The actual profile cache (ecosystem.profile.cache.vN) is written by
// useProfileSync.ts which enforces its own allowlist; this key is kept for
// legacy consumers only and must not be written with sensitive user data.
export const profileCacheStorage = new StorageItem<unknown>("sub-profile-cache")
