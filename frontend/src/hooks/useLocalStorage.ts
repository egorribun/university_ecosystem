import { useState, useCallback, useEffect, useMemo } from "react"
import { logWarning } from "@/app/logger"

export interface UseLocalStorageOptions<T> {
  serializer?: (value: T) => string
  deserializer?: (value: string) => T
  initializeWithValue?: boolean
}

const IS_BROWSER = typeof window !== "undefined"

/**
 * A custom hook to manage state synchronized with localStorage.
 * Supports SSR, event synchronization across tabs/windows, and inside the same tab.
 *
 * @param key The localStorage key.
 * @param initialValue The initial value to be used if the key doesn't exist.
 * @param options serialization options.
 */
export function useLocalStorage<T>(
  key: string,
  initialValue: T | (() => T),
  options: UseLocalStorageOptions<T> = {}
): [T, (value: T | ((val: T) => T)) => void, () => void] {
  const { initializeWithValue = true } = options
  const serializer = useMemo(
    () => (value: T) => {
      if (options.serializer) return options.serializer(value)
      return JSON.stringify(value)
    },
    [options]
  )
  const deserializer = useMemo(
    () => (value: string) => {
      if (options.deserializer) return options.deserializer(value)
      if (value === "undefined") return undefined as unknown as T
      return JSON.parse(value)
    },
    [options]
  )

  // Get value from storage, or fallback to initialValue
  // Wrapped in function to be used as useState initializer
  const readValue = useCallback((): T => {
    const initial = initialValue instanceof Function ? initialValue() : initialValue
    if (!IS_BROWSER) return initial

    try {
      const raw = window.localStorage.getItem(key)
      if (raw === null) {
        return initial
      }
      return deserializer(raw)
    } catch (e) {
      logWarning(`[useLocalStorage] Error reading key "${key}":`, { error: e })
      return initial
    }
  }, [initialValue, key, deserializer])

  const [storedValue, setStoredValue] = useState<T>(() => {
    if (initializeWithValue) return readValue()
    return initialValue instanceof Function ? initialValue() : initialValue
  })

  // Return a wrapped version of useState's setter function that ...
  // ... persists the new value to localStorage.
  const setValue = useCallback(
    (value: T | ((val: T) => T)) => {
      try {
        // Allow value to be a function so we have same API as useState
        const valueToStore = value instanceof Function ? value(storedValue) : value

        setStoredValue(valueToStore)

        const serialized = serializer(valueToStore)
        window.localStorage.setItem(key, serialized)

        // Dispatch storage event for same-tab sync. State setters returned by a
        // hook can only be invoked after a client mount; effects never run in SSR.
        window.dispatchEvent(
          new StorageEvent("storage", {
            key,
            newValue: serialized,
            url: window.location.href,
          })
        )
      } catch (e) {
        logWarning(`[useLocalStorage] Error setting key "${key}":`, { error: e })
      }
    },
    [key, storedValue, serializer]
  )

  const removeValue = useCallback(() => {
    try {
      setStoredValue(initialValue instanceof Function ? initialValue() : initialValue)
      window.localStorage.removeItem(key)
      window.dispatchEvent(
        new StorageEvent("storage", {
          key,
          newValue: null,
          url: window.location.href,
        })
      )
    } catch (e) {
      logWarning(`[useLocalStorage] Error removing key "${key}":`, { error: e })
    }
  }, [key, initialValue])

  // Sync with other tabs/windows
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === key) {
        if (e.newValue === null) {
          // If local storage is cleared, we set it to initial value
          setStoredValue(initialValue instanceof Function ? initialValue() : initialValue)
        } else {
          try {
            setStoredValue(deserializer(e.newValue))
          } catch (err) {
            logWarning("[useLocalStorage] Sync error", { error: err })
          }
        }
      }
    }

    // "storage" event only triggers on other tabs/windows by default
    // unless we manually dispatch it (which we do in setValue)
    window.addEventListener("storage", handleStorageChange)
    return () => window.removeEventListener("storage", handleStorageChange)
  }, [key, initialValue, deserializer])

  return [storedValue, setValue, removeValue]
}
