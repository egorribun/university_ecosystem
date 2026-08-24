import { openDB } from "idb"
import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { initOfflineQueue, STORES } from "../offline"

const DB_NAME = "notification-interactions"

async function createVersionThreeDatabase(withDedupeIndex: boolean) {
  const db = await openDB(DB_NAME, 3, {
    upgrade(database) {
      database.createObjectStore(STORES.NAVIGATION, { keyPath: "id", autoIncrement: true })
      const reportStore = database.createObjectStore(STORES.REPORT, {
        keyPath: "id",
        autoIncrement: true,
      })
      if (withDedupeIndex) {
        reportStore.createIndex("dedupeKey", "dedupeKey", { unique: false })
      }
      database.createObjectStore(STORES.NEWS_INTERACTION, {
        keyPath: "id",
        autoIncrement: true,
      })
      database.createObjectStore(STORES.MUTATION, { keyPath: "id", autoIncrement: true })
    },
  })
  db.close()
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
})

afterEach(() => {
  globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
})

describe("offline database upgrade", () => {
  it("adds the report deduplication index to a v3 database", async () => {
    await createVersionThreeDatabase(false)

    await initOfflineQueue()

    const upgraded = await openDB(DB_NAME, 4)
    expect(upgraded.objectStoreNames).toContain(STORES.NAVIGATION)
    expect(upgraded.objectStoreNames).toContain(STORES.REPORT)
    expect(upgraded.objectStoreNames).toContain(STORES.NEWS_INTERACTION)
    expect(upgraded.objectStoreNames).toContain(STORES.MUTATION)
    expect(upgraded.transaction(STORES.REPORT).store.indexNames).toContain("dedupeKey")
    upgraded.close()
  })

  it("preserves an existing report deduplication index", async () => {
    await createVersionThreeDatabase(true)

    await initOfflineQueue()

    const upgraded = await openDB(DB_NAME, 4)
    expect(upgraded.transaction(STORES.REPORT).store.indexNames).toContain("dedupeKey")
    upgraded.close()
  })
})
