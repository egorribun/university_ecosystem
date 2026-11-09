import { NOTIFICATION_INTERACTIONS_DB_VERSION } from "@/constants/notificationInteractionsDb"
import { openDB, unwrap } from "idb"
import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { initOfflineQueue, storePendingNavigation, STORES } from "../offline"
import { REPLAY_LEASE_STORE } from "../replayLease"

const DB_NAME = "notification-interactions"
const ALL_STORES = [...Object.values(STORES), REPLAY_LEASE_STORE].sort()

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

function observeDatabaseConnections() {
  const connections = new Set<IDBDatabase>()
  const factory = globalThis.indexedDB
  const nativeOpen = factory.open.bind(factory)
  let closing = false
  const openSpy = vi.spyOn(factory, "open").mockImplementation((...args) => {
    const request = nativeOpen(...args)
    request.addEventListener("success", () => {
      if (closing) {
        request.result.close()
      } else {
        connections.add(request.result)
      }
    })
    return request
  })

  return {
    connections,
    close() {
      closing = true
      for (const connection of connections) connection.close()
      openSpy.mockRestore()
    },
  }
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

    const db = await openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
    try {
      expect(Array.from(db.objectStoreNames).sort()).toEqual(ALL_STORES)
      expect(db.transaction(STORES.REPORT).store.indexNames.contains("dedupeKey")).toBe(true)
      const mutationIndexes = db.transaction(STORES.MUTATION).store.indexNames
      expect(Array.from(mutationIndexes).sort()).toEqual(["category", "dedupeKey", "mutationId"])
      expect(db.transaction(STORES.MUTATION).store.index("mutationId").unique).toBe(true)
    } finally {
      db.close()
    }
  })

  it("preserves an existing replay lease during a schema upgrade", async () => {
    const observer = observeDatabaseConnections()
    try {
      const legacy = await openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION - 1, {
        upgrade(database) {
          database.createObjectStore(REPLAY_LEASE_STORE, { keyPath: "id" })
          database.createObjectStore(STORES.NAVIGATION, { keyPath: "id", autoIncrement: true })
        },
      })
      const lease = { id: "replay", owner: "another-worker", expiresAt: Date.now() + 60_000 }
      await legacy.put(REPLAY_LEASE_STORE, lease)
      const navigation = { url: "/events", timestamp: 1 }
      const navigationId = await legacy.add(STORES.NAVIGATION, navigation)
      legacy.close()

      await initOfflineQueue()
      const upgraded = await openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
      try {
        expect(Array.from(upgraded.objectStoreNames).sort()).toEqual(ALL_STORES)
        expect(await upgraded.get(REPLAY_LEASE_STORE, lease.id)).toEqual(lease)
        expect(await upgraded.get(STORES.NAVIGATION, navigationId)).toEqual({
          ...navigation,
          id: navigationId,
        })
        expect(upgraded.transaction(REPLAY_LEASE_STORE).store.keyPath).toBe("id")
      } finally {
        upgraded.close()
      }
    } finally {
      observer.close()
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

    const upgraded = await openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
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

    const upgraded = await openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
    try {
      expect(Array.from(upgraded.objectStoreNames).sort()).toEqual(ALL_STORES)
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

    const upgraded = await openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
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

    const upgraded = await openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
    expect(upgraded.transaction(STORES.REPORT).store.indexNames).toContain("dedupeKey")
    upgraded.close()
  })

  it("releases production connections for a later version without losing queued data", async () => {
    const observer = observeDatabaseConnections()
    let pendingUpgrade: ReturnType<typeof openDB> | undefined

    try {
      await initOfflineQueue()
      await storePendingNavigation({ url: "/offline-upgrade-control", timestamp: 7 })

      let rejectBlocked!: (reason: Error) => void
      const blocked = new Promise<never>((_resolve, reject) => {
        rejectBlocked = reject
      })
      const transitions: Array<[number, number | null]> = []
      pendingUpgrade = openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION + 1, {
        blocked() {
          rejectBlocked(new Error("A production connection blocked the next schema version"))
        },
        upgrade(_db, oldVersion, newVersion) {
          transitions.push([oldVersion, newVersion])
        },
      })
      const upgraded = await Promise.race([pendingUpgrade, blocked])

      expect(transitions).toEqual([
        [NOTIFICATION_INTERACTIONS_DB_VERSION, NOTIFICATION_INTERACTIONS_DB_VERSION + 1],
      ])
      expect(upgraded.version).toBe(NOTIFICATION_INTERACTIONS_DB_VERSION + 1)
      expect(Array.from(upgraded.objectStoreNames).sort()).toEqual(ALL_STORES)
      expect(await upgraded.getAll(STORES.NAVIGATION)).toEqual([
        { id: 1, url: "/offline-upgrade-control", timestamp: 7, sessionNonce: null },
      ])
      expect(upgraded.transaction(STORES.REPORT).store.indexNames.contains("dedupeKey")).toBe(true)
      expect(upgraded.transaction(STORES.MUTATION).store.index("mutationId").unique).toBe(true)
    } finally {
      observer.close()
      await pendingUpgrade?.then(
        (database) => database.close(),
        () => undefined
      )
    }
  })

  it("keeps an unrelated connection blocking until its owner explicitly closes it", async () => {
    const observer = observeDatabaseConnections()
    let pendingUpgrade: ReturnType<typeof openDB> | undefined

    try {
      await initOfflineQueue()
      const blocker = await openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
      const nativeBlocker = unwrap(blocker)
      let observeBlocked!: (versions: [number, number | null]) => void
      const blocked = new Promise<[number, number | null]>((resolve) => {
        observeBlocked = resolve
      })
      let upgradeStarted = false
      pendingUpgrade = openDB(DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION + 1, {
        blocked(currentVersion, blockedVersion) {
          observeBlocked([currentVersion, blockedVersion])
        },
        upgrade() {
          upgradeStarted = true
        },
      })

      const firstEvent = await Promise.race([
        blocked.then((versions) => ({ kind: "blocked", versions })),
        pendingUpgrade.then(() => ({ kind: "upgraded" })),
      ])
      expect(firstEvent).toEqual({
        kind: "blocked",
        versions: [NOTIFICATION_INTERACTIONS_DB_VERSION, NOTIFICATION_INTERACTIONS_DB_VERSION + 1],
      })
      expect(upgradeStarted).toBe(false)

      const productionConnections = [...observer.connections].filter(
        (connection) => connection !== nativeBlocker
      )
      expect(productionConnections.length).toBeGreaterThan(0)
      for (const connection of productionConnections) {
        let failure: unknown
        try {
          connection.transaction(STORES.NAVIGATION)
        } catch (error) {
          failure = error
        }
        expect(failure).toMatchObject({ name: "InvalidStateError" })
      }
      const transaction = blocker.transaction(STORES.NAVIGATION)
      expect(await transaction.store.getAll()).toEqual([])
      await transaction.done

      blocker.close()
      const upgraded = await pendingUpgrade
      expect(upgradeStarted).toBe(true)
      expect(upgraded.version).toBe(NOTIFICATION_INTERACTIONS_DB_VERSION + 1)
      expect(Array.from(upgraded.objectStoreNames).sort()).toEqual(ALL_STORES)
    } finally {
      observer.close()
      await pendingUpgrade?.then(
        (database) => database.close(),
        () => undefined
      )
    }
  })
})
