
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
    } catch (e) {
      console.warn(`[Storage] Failed to parse key "${this.key}":`, e)
      return this.fallback
    }
  }

  /**
   * Writes the value to localStorage.
   */
  set(value: T): void {
    if (!IS_BROWSER) return
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
    } catch (e) {
      console.warn(`[Storage] Failed to set key "${this.key}":`, e)
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
    } catch (e) {
      console.warn(`[Storage] Failed to remove key "${this.key}":`, e)
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
export const profileCacheStorage = new StorageItem<unknown>("sub-profile-cache")
