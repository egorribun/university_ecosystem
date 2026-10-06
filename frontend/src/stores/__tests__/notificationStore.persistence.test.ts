import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

describe("notification preference persistence", () => {
  const storageKey = "notification-preferences"

  beforeEach(() => {
    localStorage.removeItem(storageKey)
    vi.resetModules()
  })

  afterEach(() => {
    localStorage.removeItem(storageKey)
    vi.resetModules()
  })

  it("restores topic choices without persisting permission or transient toasts", async () => {
    const firstModule = await import("@/stores/notificationStore")
    const firstStore = firstModule.useNotificationStore

    firstStore.getState().setTopic("schedule.changed", false)
    firstStore.getState().setPermission("granted")
    firstStore.getState().addToast("Transient notification")

    const serialized = localStorage.getItem(storageKey)
    expect(serialized).not.toBeNull()
    const persisted = JSON.parse(serialized!) as {
      state: Record<string, unknown>
      version: number
    }
    expect(persisted.version).toBe(2)
    expect(persisted.state).toEqual({
      topics: {
        "news.published": true,
        "schedule.changed": false,
        "events.published": true,
        "chat.message.created": true,
        "system.release": true,
      },
    })

    vi.resetModules()
    const restoredModule = await import("@/stores/notificationStore")
    const restoredStore = restoredModule.useNotificationStore
    await restoredStore.persist.rehydrate()

    expect(restoredStore.getState().topics["schedule.changed"]).toBe(false)
    expect(restoredStore.getState().topics["news.published"]).toBe(true)
    expect(restoredStore.getState().permission).toBe("default")
    expect(restoredStore.getState().toasts).toEqual([])
  })
})
