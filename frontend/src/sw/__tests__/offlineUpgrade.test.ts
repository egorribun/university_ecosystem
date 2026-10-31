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
  it("creates the complete shared schema when the worker initializes a fresh database", async () => {
    await initOfflineQueue()

    const db = await openDB(DB_NAME, 4)
    try {
      expect(Array.from(db.objectStoreNames).sort()).toEqual(Object.values(STORES).sort())
      expect(db.transaction(STORES.REPORT).store.indexNames.contains("dedupeKey")).toBe(true)
      const mutationIndexes = db.transaction(STORES.MUTATION).store.indexNames
      expect(Array.from(mutationIndexes).sort()).toEqual(["category", "dedupeKey", "mutationId"])
      expect(db.transaction(STORES.MUTATION).store.index("mutationId").unique).toBe(true)
    } finally {
      db.close()
    }
  })

  it("preserves all legacy queue records when upgrading from version 3", async () => {
    await createVersionThreeDatabase(false)
    const oldDb = await openDB(DB_NAME, 3)
    const navigation = { url: "/private", timestamp: 1 }
    const report = { reportUrl: "/api/report", method: "POST", payload: { action: "click" } }
    const news = { url: "/api/v1/news/1/comment", method: "POST", payload: { content: "draft" } }
    const mutation = { url: "/api/v1/profile", method: "PATCH", payload: { value: "draft" } }
    await oldDb.add(STORES.NAVIGATION, navigation)
    await oldDb.add(STORES.REPORT, report)
    await oldDb.add(STORES.NEWS_INTERACTION, news)
    await oldDb.add(STORES.MUTATION, mutation)
    oldDb.close()

    await initOfflineQueue()

    const upgraded = await openDB(DB_NAME, 4)
    try {
      expect(await upgraded.getAll(STORES.NAVIGATION)).toEqual([{ ...navigation, id: 1 }])
      expect(await upgraded.getAll(STORES.REPORT)).toEqual([{ ...report, id: 1 }])
      expect(await upgraded.getAll(STORES.NEWS_INTERACTION)).toEqual([{ ...news, id: 1 }])
      expect(await upgraded.getAll(STORES.MUTATION)).toEqual([{ ...mutation, id: 1 }])
      expect(upgraded.transaction(STORES.REPORT).store.indexNames.contains("dedupeKey")).toBe(true)
    } finally {
      upgraded.close()
    }
  })

  it("upgrades the historical page-created v3 schema without losing its three queues", async () => {
    const pageDb = await openDB(DB_NAME, 3, {
      upgrade(database) {
        database.createObjectStore(STORES.NAVIGATION, { keyPath: "id", autoIncrement: true })
        database.createObjectStore(STORES.REPORT, { keyPath: "id", autoIncrement: true })
        database.createObjectStore(STORES.NEWS_INTERACTION, { keyPath: "id", autoIncrement: true })
      },
    })
    const navigation = { url: "/private", timestamp: 1 }
    const report = { reportUrl: "/api/report", method: "POST", payload: { action: "click" } }
    const news = { url: "/api/v1/news/1/comment", method: "POST", payload: { content: "draft" } }
    await pageDb.add(STORES.NAVIGATION, navigation)
    await pageDb.add(STORES.REPORT, report)
    await pageDb.add(STORES.NEWS_INTERACTION, news)
    pageDb.close()

    await initOfflineQueue()

    const upgraded = await openDB(DB_NAME, 4)
    try {
      expect(Array.from(upgraded.objectStoreNames).sort()).toEqual(Object.values(STORES).sort())
      expect(await upgraded.getAll(STORES.NAVIGATION)).toEqual([{ ...navigation, id: 1 }])
      expect(await upgraded.getAll(STORES.REPORT)).toEqual([{ ...report, id: 1 }])
      expect(await upgraded.getAll(STORES.NEWS_INTERACTION)).toEqual([{ ...news, id: 1 }])
      expect(await upgraded.getAll(STORES.MUTATION)).toEqual([])
      expect(upgraded.transaction(STORES.REPORT).store.indexNames.contains("dedupeKey")).toBe(true)
      expect(Array.from(upgraded.transaction(STORES.MUTATION).store.indexNames).sort()).toEqual([
        "category",
        "dedupeKey",
        "mutationId",
      ])
      expect(upgraded.transaction(STORES.MUTATION).store.index("mutationId").unique).toBe(true)
    } finally {
      upgraded.close()
    }
  })

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
