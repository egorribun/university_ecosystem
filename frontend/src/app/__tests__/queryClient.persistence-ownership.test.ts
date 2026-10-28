import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { dehydrate, hydrate, type QueryKey } from "@tanstack/react-query"
import {
  persistQueryClientRestore,
  persistQueryClientSave,
  type PersistedClient,
} from "@tanstack/react-query-persist-client"
import { clear, del, get, keys, set } from "idb-keyval"
import {
  acceptBrowserSessionGeneration,
  captureSessionEpoch,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { ENCRYPTED_CACHE_PLACEHOLDER_USER_ID, SSR_STUB_USER_ID } from "@/stores/authIdentity"
import { testUser } from "@/tests/mocks/handlers"
import type { UserState } from "@/types/Auth"
import { anonymousNewsListQueryKey, newsListQueryKey } from "@/api/hooks/news"

// Keep real IndexedDB transactions and structured cloning. Only the delivery of
// an operation's result is held, so account transitions can occur while the
// application is still awaiting the browser's response.
const io = vi.hoisted(() => ({
  afterKeys: undefined as undefined | (() => Promise<void>),
  afterRead: undefined as undefined | ((key: IDBValidKey) => Promise<void>),
  afterWrite: undefined as undefined | ((key: IDBValidKey) => Promise<void>),
  beforeDelete: undefined as undefined | ((key: IDBValidKey) => Promise<void>),
  readError: undefined as Error | undefined,
  writeError: undefined as Error | undefined,
}))
vi.mock("idb-keyval", async (importOriginal) => {
  const actual = await importOriginal<typeof import("idb-keyval")>()
  return {
    ...actual,
    keys: async () => {
      const result = await actual.keys()
      await io.afterKeys?.()
      return result
    },
    get: async (key: IDBValidKey) => {
      if (io.readError) throw io.readError
      const result = await actual.get(key)
      await io.afterRead?.(key)
      return result
    },
    set: async (key: IDBValidKey, value: unknown) => {
      if (io.writeError) throw io.writeError
      await actual.set(key, value)
      await io.afterWrite?.(key)
    },
    del: async (key: IDBValidKey) => {
      await io.beforeDelete?.(key)
      await actual.del(key)
    },
  }
})

import {
  createQueryClient,
  idbPersister,
  persistOptions,
  setQueryCacheIdentity,
} from "../queryClient"

const sessionKey = "ecosystem.session.generation.v1"
const accountKey = (owner: string) => `reactQuery:v2:${encodeURIComponent(owner)}`

function publishAccount(id: string | null) {
  useAuthStore.setState({
    user: id === null ? null : { ...testUser, id },
    loading: false,
  })
}

function snapshot(owner: string, profileKey: QueryKey = ["users", "me"]): PersistedClient {
  const source = createQueryClient()
  source.setQueryData(profileKey, { ...testUser, id: owner })
  source.setQueryData(["schedule"], [`schedule for ${owner}`])
  const saved = {
    timestamp: Date.now(),
    buster: "1.0.0",
    clientState: dehydrate(source),
  }
  source.clear()
  return saved
}

function appendQueryData(
  saved: PersistedClient,
  queryKey: QueryKey,
  data: unknown,
  meta?: Record<string, unknown>
): PersistedClient {
  const source = createQueryClient()
  if (meta) source.setQueryDefaults(queryKey, { meta })
  source.setQueryData(queryKey, data)
  const query = dehydrate(source).queries[0]
  if (!query) throw new Error("Expected a dehydrated query")
  source.clear()

  return {
    ...saved,
    clientState: {
      ...saved.clientState,
      queries: [...saved.clientState.queries, query],
    },
  }
}
function withDuplicateProfileWitnesses(
  saved: PersistedClient,
  witnessIds: readonly (string | null)[]
): PersistedClient {
  const profile = saved.clientState.queries.find(
    (query) => query.queryKey[0] === "users" && query.queryKey[1] === "me"
  )
  if (!profile) throw new Error("Expected a current-user profile query")

  const profileData = profile.state.data as Record<string, unknown>
  const duplicates = witnessIds.map((id) => ({
    ...profile,
    state: {
      ...profile.state,
      data: id === null ? null : { ...profileData, id },
    },
  }))

  return {
    ...saved,
    clientState: {
      ...saved.clientState,
      queries: [...duplicates, ...saved.clientState.queries.filter((query) => query !== profile)],
    },
  }
}

const duplicateProfileWitnessCases = [
  {
    label: "A-owned cache with A before B",
    activeOwner: "A",
    dataOwner: "B",
    witnessIds: ["A", "B"],
  },
  {
    label: "B-owned cache with B before A",
    activeOwner: "B",
    dataOwner: "A",
    witnessIds: ["B", "A"],
  },
  {
    label: "duplicate witnesses for the same owner",
    activeOwner: "A",
    dataOwner: "A",
    witnessIds: ["A", "A"],
  },
  {
    label: "malformed second witness",
    activeOwner: "A",
    dataOwner: "B",
    witnessIds: ["A", null],
  },
] as const

function withoutCurrentUserProfile(saved: PersistedClient): PersistedClient {
  return {
    ...saved,
    clientState: {
      ...saved.clientState,
      queries: saved.clientState.queries.filter(
        (query) => !(query.queryKey[0] === "users" && query.queryKey[1] === "me")
      ),
    },
  }
}

function pause() {
  let release!: () => void
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  let entered = false
  return {
    hold: async () => {
      entered = true
      await pending
    },
    entered: () => entered,
    release,
  }
}

beforeEach(async () => {
  io.afterKeys = undefined
  io.afterRead = undefined
  io.afterWrite = undefined
  io.beforeDelete = undefined
  io.readError = undefined
  io.writeError = undefined
  rotateBrowserSession()
  publishAccount(null)
  await clear()
})

afterEach(async () => {
  io.afterKeys = undefined
  io.afterRead = undefined
  io.afterWrite = undefined
  io.beforeDelete = undefined
  io.readError = undefined
  io.writeError = undefined
  publishAccount(null)
  await clear()
})

describe("profile persistence boundaries", () => {
  it("rejects a profile whose owner conflicts with the confirmed cache identity", async () => {
    publishAccount("A")
    const otherOwnersProfile = snapshot("B")

    await idbPersister.persistClient(otherOwnersProfile)
    expect(await keys()).toEqual([])

    await set(accountKey("A"), otherOwnersProfile)
    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
  })

  it.each(duplicateProfileWitnessCases)(
    "rejects ambiguous duplicate profile witnesses during persistence ($label)",
    async ({ activeOwner, dataOwner, witnessIds }) => {
      publishAccount(activeOwner)
      setQueryCacheIdentity(activeOwner)
      acceptBrowserSessionGeneration()

      const ambiguousSnapshot = withDuplicateProfileWitnesses(snapshot(dataOwner), witnessIds)
      await idbPersister.persistClient(ambiguousSnapshot)

      expect(await keys()).toEqual([])
    }
  )

  it.each(duplicateProfileWitnessCases)(
    "purges ambiguous duplicate profile witnesses during legacy restore ($label)",
    async ({ activeOwner, dataOwner, witnessIds }) => {
      publishAccount(activeOwner)
      setQueryCacheIdentity(activeOwner)
      acceptBrowserSessionGeneration()

      const ambiguousSnapshot = withDuplicateProfileWitnesses(snapshot(dataOwner), witnessIds)
      await set(accountKey(activeOwner), ambiguousSnapshot)

      await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
      expect(await get<PersistedClient>(accountKey(activeOwner))).toBeUndefined()
      expect(await keys()).toEqual([])
    }
  )

  it("does not infer a browser owner from profile data alone", async () => {
    publishAccount(null)
    const source = createQueryClient()
    source.setQueryData(["users", "me"], { ...testUser, id: "A" })
    source.setQueryData(["schedule"], ["unconfirmed schedule"])
    const saved = {
      timestamp: Date.now(),
      buster: "1.0.0",
      clientState: dehydrate(source, { shouldDehydrateQuery: () => true }),
    }
    source.clear()

    await expect(idbPersister.persistClient(saved)).resolves.toBeUndefined()
    expect(await keys()).toEqual([])
    await set(accountKey("A"), saved)
    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
  })

  it("fails closed for malformed persisted snapshots before filtering", async () => {
    const valid = snapshot("A")
    const malformedSnapshots: unknown[] = [
      null,
      {},
      { ...valid, timestamp: Number.NaN },
      { ...valid, timestamp: Number.POSITIVE_INFINITY },
      {
        ...valid,
        clientState: {
          ...valid.clientState,
          queries: valid.clientState.queries.map((query, index) =>
            index === 0 ? { ...query, dehydratedAt: Number.NaN } : query
          ),
        },
      },
      {
        ...valid,
        clientState: {
          ...valid.clientState,
          queries: valid.clientState.queries.map((query, index) =>
            index === 0 ? { ...query, dehydratedAt: Number.POSITIVE_INFINITY } : query
          ),
        },
      },
      { clientState: null },
      { clientState: { queries: null, mutations: [] } },
      { ...valid, clientState: { ...valid.clientState, queries: null } },
      {
        ...valid,
        clientState: {
          ...valid.clientState,
          queries: [null, ...valid.clientState.queries],
        },
      },
      { ...valid, clientState: { ...valid.clientState, mutations: null } },
      {
        ...valid,
        clientState: {
          ...valid.clientState,
          mutations: [null, ...valid.clientState.mutations],
        },
      },
      {
        ...valid,
        clientState: {
          ...valid.clientState,
          mutations: [{ mutationKey: { invalid: true }, state: {} }],
        },
      },
      {
        ...valid,
        clientState: {
          ...valid.clientState,
          mutations: [{ state: {}, meta: [] }],
        },
      },
    ]

    for (const malformed of malformedSnapshots) {
      await expect(
        idbPersister.persistClient(malformed as PersistedClient)
      ).resolves.toBeUndefined()
    }
    expect(await keys()).toEqual([])

    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()
    for (const malformed of malformedSnapshots) {
      await expect(
        idbPersister.persistClient(malformed as PersistedClient)
      ).resolves.toBeUndefined()
    }
    expect(await keys()).toEqual([])

    for (const malformed of malformedSnapshots) {
      await set(accountKey("A"), malformed)
      await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
    }
  })

  it("round-trips valid pending mutations with optional fields omitted or shaped", async () => {
    publishAccount("A")
    const base = snapshot("A")
    const state = {
      context: undefined,
      data: undefined,
      error: null,
      failureCount: 0,
      failureReason: null,
      isPaused: true,
      status: "pending" as const,
      variables: { scheduleId: "schedule-1" },
      submittedAt: Date.now(),
    }
    const optionalFieldsOmitted = {
      state,
    } satisfies PersistedClient["clientState"]["mutations"][number]
    const optionalFieldsPresent = {
      mutationKey: ["schedule", "create"],
      meta: { persist: true },
      state,
    } satisfies PersistedClient["clientState"]["mutations"][number]
    const saved: PersistedClient = {
      ...base,
      clientState: {
        ...base.clientState,
        mutations: [optionalFieldsOmitted, optionalFieldsPresent],
      },
    }

    await idbPersister.persistClient(saved)
    const persisted = await get<PersistedClient>(accountKey("A"))
    expect(persisted?.clientState.mutations).toEqual([optionalFieldsOmitted, optionalFieldsPresent])
    expect(persisted?.clientState.mutations[0]).not.toHaveProperty("mutationKey")
    expect(persisted?.clientState.mutations[0]).not.toHaveProperty("meta")

    const restored = await idbPersister.restoreClient()
    expect(restored?.clientState.mutations).toEqual([optionalFieldsOmitted, optionalFieldsPresent])
  })

  it("omits full profiles from durable snapshots while retaining memory and offline state", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()

    const source = createQueryClient()
    const bootstrapKey = ["auth", "bootstrap", "current-user", "scope", 2, 7] as const
    const profileEmail = "profile-pii-sentinel@example.invalid"
    const ownedProfile = { ...testUser, id: "A", email: profileEmail }
    const stagedProfile = {
      ...testUser,
      id: "staged-bootstrap-profile-id",
      email: "staged-bootstrap-profile@example.invalid",
    }
    source.setQueryDefaults(bootstrapKey, { meta: { persist: false } })
    source.setQueryData(["users", "me"], ownedProfile)
    source.setQueryData(bootstrapKey, stagedProfile)
    source.setQueryData(["schedule"], ["offline schedule A"])
    source.getMutationCache().build(
      source,
      { mutationKey: ["schedule", "create"], meta: { persist: true } },
      {
        context: undefined,
        data: undefined,
        error: null,
        failureCount: 0,
        failureReason: null,
        isPaused: true,
        status: "pending",
        variables: { scheduleId: "offline-schedule-A" },
        submittedAt: Date.now(),
      }
    )

    const configuredSnapshot = dehydrate(source, persistOptions.dehydrateOptions)
    expect(configuredSnapshot.queries.some((query) => query.queryKey[0] === "auth")).toBe(false)
    expect(
      configuredSnapshot.queries.some(
        (query) => query.queryKey[0] === "users" && query.queryKey[1] === "me"
      )
    ).toBe(false)
    expect(source.getQueryData(["users", "me"])).toEqual(ownedProfile)
    expect(
      configuredSnapshot.queries.find((query) => query.queryKey[0] === "schedule")?.state.data
    ).toEqual(["offline schedule A"])

    // Exercise the defensive boundary even if a caller dehydrates every query.
    const inclusiveSnapshot = dehydrate(source, {
      shouldDehydrateQuery: () => true,
    })
    expect(inclusiveSnapshot.queries.some((query) => query.queryKey[0] === "auth")).toBe(true)
    await idbPersister.persistClient({
      timestamp: Date.now(),
      buster: "1.0.0",
      clientState: inclusiveSnapshot,
    })

    const saved = await get<PersistedClient>(accountKey("A"))
    expect(saved).toBeDefined()
    expect(saved!.clientState.queries.some((query) => query.queryKey[0] === "auth")).toBe(false)
    expect(
      saved!.clientState.queries.some(
        (query) => query.queryKey[0] === "users" && query.queryKey[1] === "me"
      )
    ).toBe(false)
    expect(JSON.stringify(saved)).not.toContain(profileEmail)
    expect(JSON.stringify(saved)).not.toContain(stagedProfile.email)
    expect(
      saved!.clientState.queries.find((query) => query.queryKey[0] === "schedule")?.state.data
    ).toEqual(["offline schedule A"])
    expect(saved!.clientState.mutations[0]?.state.variables).toEqual({
      scheduleId: "offline-schedule-A",
    })
    source.clear()
  })

  it("rejects malformed news list states before hydrate and preserves valid owner data", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()

    const validEmptyKey = newsListQueryKey({ language: "en", limit: 12 })
    const emptyCollectionKey = newsListQueryKey({
      language: "no-pages",
      limit: 12,
    })
    const validCursorKey = newsListQueryKey({ language: "cursor", limit: 12 })
    const validEmptyData = {
      pages: [{ items: [], cursor: null, next_cursor: null, has_more: false }],
      pageParams: [null],
    }
    const validCursorData = {
      pages: [{ items: [], cursor: "page-1", next_cursor: "page-2" }],
      pageParams: ["page-1"],
    }
    const emptyCollectionData = { pages: [], pageParams: [] }
    const uncheckedItemsKey = newsListQueryKey({
      language: "unchecked-items",
      limit: 12,
    })
    const uncheckedItemsData = {
      pages: [
        {
          items: [{ id: "malformed-article" }],
          total: "invalid-total",
          limit: "invalid-limit",
          cursor: null,
          next_cursor: null,
          has_more: false,
        },
      ],
      pageParams: [null],
    }
    const malformedQueries = [
      {
        key: newsListQueryKey({ language: "primitive", limit: 12 }),
        data: "malformed-data",
      },
      { key: newsListQueryKey({ language: "null", limit: 12 }), data: null },
      {
        key: newsListQueryKey({ language: "pages", limit: 12 }),
        data: { pages: "malformed-pages", pageParams: [] },
      },
      {
        key: anonymousNewsListQueryKey({ language: "params", limit: 12 }),
        data: { pages: [{ items: [] }], pageParams: "malformed-page-params" },
      },
      {
        key: newsListQueryKey({ language: "mismatch", limit: 12 }),
        data: { pages: [{ items: [] }], pageParams: [] },
      },
      {
        key: newsListQueryKey({ language: "null-page", limit: 12 }),
        data: { pages: [null], pageParams: [null] },
      },
      {
        key: newsListQueryKey({ language: "items", limit: 12 }),
        data: { pages: [{ items: "malformed-items" }], pageParams: [null] },
      },
      {
        key: newsListQueryKey({ language: "bad-next-cursor", limit: 12 }),
        data: {
          pages: [{ items: [], next_cursor: { cursor: "bad" } }],
          pageParams: [null],
        },
      },
      {
        key: newsListQueryKey({ language: "has-more", limit: 12 }),
        data: { pages: [{ items: [], has_more: "bad" }], pageParams: [null] },
      },
      {
        key: newsListQueryKey({ language: "param-value", limit: 12 }),
        data: { pages: [{ items: [] }], pageParams: [{}] },
      },
      {
        key: newsListQueryKey({ language: "sparse-pages", limit: 12 }),
        data: { pages: Array(1), pageParams: [null] },
      },
      {
        key: newsListQueryKey({ language: "sparse-params", limit: 12 }),
        data: { pages: [{ items: [] }], pageParams: Array(1) },
      },
    ] as const
    const nearMisses = [
      {
        key: ["news", "list", "not-normalized"],
        data: "preserve non-list key",
      },
      {
        key: ["news", "list", { language: 3, limit: 12 }],
        data: "preserve invalid language type",
      },
      {
        key: ["news", "list", "en", 12],
        data: "preserve non-exact key length",
      },
      {
        key: ["news", "list", { language: "en", limit: "12" }],
        data: "preserve invalid limit type",
      },
      {
        key: ["news", "list", { language: "en", limit: 0 }],
        data: "preserve non-positive limit",
      },
      {
        key: ["news", "list", { language: "en", limit: 1.5 }],
        data: "preserve non-integer limit",
      },
      { key: ["news", "detail", "article-id"], data: "preserve detail query" },
      {
        key: ["schedule", "list", "owner-A"],
        data: "preserve unrelated query",
      },
    ] as const

    let saved = snapshot("A")
    for (const query of malformedQueries) saved = appendQueryData(saved, query.key, query.data)
    for (const query of nearMisses) saved = appendQueryData(saved, query.key, query.data)
    saved = appendQueryData(saved, emptyCollectionKey, emptyCollectionData)
    saved = appendQueryData(saved, validEmptyKey, validEmptyData, {
      persist: true,
      source: "news-list",
    })
    saved = appendQueryData(saved, validCursorKey, validCursorData)
    saved = appendQueryData(saved, uncheckedItemsKey, uncheckedItemsData)
    await set(accountKey("A"), saved)

    const restored = await idbPersister.restoreClient()
    expect(restored).toBeDefined()
    const queryIds = restored!.clientState.queries.map((query) => JSON.stringify(query.queryKey))
    for (const malformed of malformedQueries) {
      expect(queryIds).not.toContain(JSON.stringify(malformed.key))
    }
    for (const retained of nearMisses) {
      expect(queryIds).toContain(JSON.stringify(retained.key))
    }
    expect(queryIds).toContain(JSON.stringify(emptyCollectionKey))
    expect(queryIds).toContain(JSON.stringify(validCursorKey))
    expect(queryIds).toContain(JSON.stringify(uncheckedItemsKey))
    expect(
      restored!.clientState.queries.find(
        (query) => JSON.stringify(query.queryKey) === JSON.stringify(validEmptyKey)
      )?.meta
    ).toEqual({ persist: true, source: "news-list" })
    expect(
      restored!.clientState.queries.find(
        (query) => JSON.stringify(query.queryKey) === JSON.stringify(validEmptyKey)
      )?.state.data
    ).toEqual(validEmptyData)
    expect(
      restored!.clientState.queries.find((query) => query.queryKey[0] === "schedule")?.state.data
    ).toEqual(["schedule for A"])

    const stored = await get<PersistedClient>(accountKey("A"))
    expect(stored).toBeDefined()
    expect(stored!.clientState.queries.map((query) => JSON.stringify(query.queryKey))).toEqual(
      queryIds
    )
    const target = createQueryClient()
    hydrate(target, restored!.clientState)
    expect(target.getQueryData(emptyCollectionKey)).toEqual(emptyCollectionData)
    expect(target.getQueryData(uncheckedItemsKey)).toEqual(uncheckedItemsData)
    for (const malformed of malformedQueries) {
      expect(target.getQueryData(malformed.key)).toBeUndefined()
    }
    target.clear()
  })
  it("sanitizes a dormant legacy v2 profile before restoring offline state", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()

    const legacy = snapshot("B")
    const profileEmail = "legacy-profile-pii-sentinel@example.invalid"
    const profile = legacy.clientState.queries.find(
      (query) => query.queryKey[0] === "users" && query.queryKey[1] === "me"
    )
    if (!profile) throw new Error("Expected a legacy full-profile query")
    profile.state.data = { ...testUser, id: "B", email: profileEmail }
    const pausedMutation = {
      mutationKey: ["schedule", "create"],
      meta: { persist: true },
      state: {
        context: undefined,
        data: undefined,
        error: null,
        failureCount: 0,
        failureReason: null,
        isPaused: true,
        status: "pending" as const,
        variables: { scheduleId: "offline-schedule-B" },
        submittedAt: Date.now(),
      },
    } satisfies PersistedClient["clientState"]["mutations"][number]
    legacy.clientState.mutations.push(pausedMutation)
    await set(accountKey("B"), legacy)

    // A restore attempt for A also sanitizes dormant snapshots before any
    // account snapshot can later be returned for hydration.
    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
    const sanitizedDormant = await get<PersistedClient>(accountKey("B"))
    expect(sanitizedDormant).toEqual(withoutCurrentUserProfile(legacy))
    expect(JSON.stringify(sanitizedDormant)).not.toContain(profileEmail)
    expect(
      sanitizedDormant!.clientState.queries.find((query) => query.queryKey[0] === "schedule")?.state
        .data
    ).toEqual(["schedule for B"])
    expect(sanitizedDormant!.clientState.mutations[0]?.state.variables).toEqual({
      scheduleId: "offline-schedule-B",
    })

    publishAccount("B")
    setQueryCacheIdentity("B")
    const restored = await idbPersister.restoreClient()
    expect(restored).toBeDefined()
    expect(
      restored!.clientState.queries.some(
        (query) => query.queryKey[0] === "users" && query.queryKey[1] === "me"
      )
    ).toBe(false)
    expect(JSON.stringify(restored)).not.toContain(profileEmail)
    expect(
      restored!.clientState.queries.find((query) => query.queryKey[0] === "schedule")?.state.data
    ).toEqual(["schedule for B"])
    expect(restored!.clientState.mutations[0]?.state.variables).toEqual({
      scheduleId: "offline-schedule-B",
    })

    const migrated = await get<PersistedClient>(accountKey("B"))
    expect(migrated).toBeDefined()
    expect(
      migrated!.clientState.queries.some(
        (query) => query.queryKey[0] === "users" && query.queryKey[1] === "me"
      )
    ).toBe(false)
    expect(JSON.stringify(migrated)).not.toContain(profileEmail)
    expect(migrated!.clientState.mutations[0]?.state.variables).toEqual({
      scheduleId: "offline-schedule-B",
    })
  })

  it("keeps account namespaces distinct when an id contains reserved URL characters", async () => {
    publishAccount("A/B:C")
    await idbPersister.persistClient(snapshot("A/B:C"))
    expect(await keys()).toEqual(["reactQuery:v2:A%2FB%3AC"])
    const restored = await idbPersister.restoreClient()
    const target = createQueryClient()
    hydrate(target, restored!.clientState)
    expect(target.getQueryData(["schedule"])).toEqual(["schedule for A/B:C"])
  })

  it("deletes malformed owner keys without touching unrelated IndexedDB keys", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()

    const malformedKeys = ["reactQuery:v2:", "reactQuery:v2:%ZZ", "reactQuery:v2:A%2fB"]
    const saved = snapshot("A")
    for (const key of malformedKeys) await set(key, saved)
    await set(7, saved)

    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()

    for (const key of malformedKeys) {
      await expect(get<PersistedClient>(key)).resolves.toBeUndefined()
    }
    expect(await get<PersistedClient>(7)).toEqual(saved)
    expect(await keys()).toEqual([7])
  })

  it("stops dormant-key migration when cache ownership changes during enumeration", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()
    const dormant = snapshot("B")
    await set(accountKey("B"), dormant)

    io.afterKeys = async () => {
      io.afterKeys = undefined
      publishAccount("B")
    }

    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
    expect(await get<PersistedClient>(accountKey("B"))).toEqual(dormant)
  })

  it("skips a persisted key deleted after enumeration", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()
    const key = accountKey("A")
    await set(key, snapshot("A"))

    io.afterKeys = async () => {
      io.afterKeys = undefined
      await del(key)
    }

    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
    expect(await get<PersistedClient>(key)).toBeUndefined()
  })

  it("sanitizes a current snapshot added after legacy enumeration", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()
    const key = accountKey("A")
    const lateLegacySnapshot = snapshot("A")

    io.afterKeys = async () => {
      io.afterKeys = undefined
      await set(key, lateLegacySnapshot)
    }

    const restored = await idbPersister.restoreClient()
    expect(restored).toEqual(withoutCurrentUserProfile(lateLegacySnapshot))
    expect(await get<PersistedClient>(key)).toEqual(withoutCurrentUserProfile(lateLegacySnapshot))
  })

  it("fails restore on a sanitation write error and recovers its persistence queue", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()
    const key = accountKey("A")
    const legacySnapshot = snapshot("A")
    const writeError = new Error("IndexedDB write unavailable")

    io.afterKeys = async () => {
      io.afterKeys = undefined
      await set(key, legacySnapshot)
      io.writeError = writeError
    }

    await expect(idbPersister.restoreClient()).rejects.toBe(writeError)
    io.writeError = undefined
    await expect(get<PersistedClient>(key)).resolves.toEqual(legacySnapshot)

    const restored = await idbPersister.restoreClient()
    const sanitized = withoutCurrentUserProfile(legacySnapshot)
    expect(restored).toEqual(sanitized)
    expect(await get<PersistedClient>(key)).toEqual(sanitized)
  })

  it("continues queued persistence after an IndexedDB save rejects", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()
    const key = accountKey("A")
    const failure = new Error("IndexedDB write unavailable")

    io.writeError = failure
    await expect(idbPersister.persistClient(snapshot("A"))).rejects.toBe(failure)
    expect(await get<PersistedClient>(key)).toBeUndefined()

    io.writeError = undefined
    const nextSnapshot = snapshot("A")
    await expect(idbPersister.persistClient(nextSnapshot)).resolves.toBeUndefined()
    expect(await get<PersistedClient>(key)).toEqual(withoutCurrentUserProfile(nextSnapshot))
  })
  it("does not write a restore-time sanitized snapshot after its owner changes", async () => {
    publishAccount("A")
    setQueryCacheIdentity("A")
    acceptBrowserSessionGeneration()
    const key = accountKey("A")
    const lateLegacySnapshot = snapshot("A")
    const heldWrite = pause()
    let queuedWrite: Promise<void> | undefined
    let interceptedRead = false
    let interceptedWrite = false
    let allowWritePause = false

    io.afterKeys = async () => {
      io.afterKeys = undefined
      await set(key, lateLegacySnapshot)
      allowWritePause = true
    }
    io.afterRead = async (readKey) => {
      if (interceptedRead || readKey !== key) return
      interceptedRead = true
      queuedWrite = Promise.resolve(idbPersister.persistClient(snapshot("A")))
    }
    io.afterWrite = async (writeKey) => {
      if (!allowWritePause || interceptedWrite || writeKey !== key) return
      interceptedWrite = true
      await heldWrite.hold()
    }

    const restoring = idbPersister.restoreClient()
    try {
      await vi.waitFor(() => expect(heldWrite.entered()).toBe(true))
      publishAccount("B")
      heldWrite.release()
      await expect(restoring).resolves.toBeUndefined()
      if (!queuedWrite) throw new Error("Expected the queued account write")
      await expect(queuedWrite).resolves.toBeUndefined()
      expect(await get<PersistedClient>(key)).toBeUndefined()
    } finally {
      heldWrite.release()
      io.afterKeys = undefined
      io.afterRead = undefined
      io.afterWrite = undefined
      await Promise.allSettled([restoring, ...(queuedWrite ? [queuedWrite] : [])])
    }
  })

  it("keeps confirmed in-memory data during an ordinary same-account refresh", async () => {
    publishAccount("A")
    const active = createQueryClient()
    active.setQueryData(["schedule"], ["current schedule"])
    const owns = captureSessionEpoch()

    useAuthStore.setState({ loading: true })
    expect(active.getQueryData(["schedule"])).toEqual(["current schedule"])
    expect(owns()).toBe(true)
    await idbPersister.persistClient(snapshot("A"))
    expect(await get(accountKey("A"))).toBeDefined()

    useAuthStore.setState({ loading: false })
    expect(active.getQueryData(["schedule"])).toEqual(["current schedule"])
    expect(owns()).toBe(true)
  })

  it("retires the old cache when a different profile is still loading", async () => {
    publishAccount("A")
    const active = createQueryClient()
    active.setQueryData(["schedule"], ["old schedule"])
    const outgoing = snapshot("A")
    useAuthStore.setState({ user: { ...testUser, id: "B" }, loading: true })

    expect(active.getQueryCache().getAll()).toEqual([])
    await idbPersister.persistClient(outgoing)
    expect(await keys()).toEqual([])
  })

  it("invalidates suspended work when identity changes without rotating the browser session", async () => {
    publishAccount("A")
    const active = createQueryClient()
    const canceling = active.cancelQueries()
    // Profile publication precedes rendering and need not be accompanied by a
    // browser-generation update, for example during an auth refresh.
    publishAccount("B")
    await expect(canceling).rejects.toMatchObject({ silent: true })
  })

  it("requires a browser generation even when network auth confirms the profile", async () => {
    localStorage.removeItem(sessionKey)
    acceptBrowserSessionGeneration()
    publishAccount("A")
    const saved = snapshot("A")
    await idbPersister.persistClient(saved)
    expect(await keys()).toEqual([])

    await set(accountKey("A"), saved)
    await set("reactQuery", saved)
    expect(await idbPersister.restoreClient()).toBeUndefined()
    expect(await get("reactQuery")).toBeUndefined()
  })

  it("restores the profile confirmed while legacy deletion was pending", async () => {
    const saved = snapshot("A")
    await set(accountKey("A"), saved)
    useAuthStore.setState({
      user: { ...testUser, id: "ssr-stub" },
      loading: true,
    })
    const legacyDeletion = pause()
    io.beforeDelete = legacyDeletion.hold
    const restoring = idbPersister.restoreClient()
    try {
      await vi.waitFor(() => expect(legacyDeletion.entered()).toBe(true))
      legacyDeletion.release()
      publishAccount("A")
      expect(await restoring).toEqual(withoutCurrentUserProfile(saved))
      expect(await get(accountKey("A"))).toEqual(withoutCurrentUserProfile(saved))
    } finally {
      legacyDeletion.release()
      publishAccount(null)
      await Promise.allSettled([restoring])
    }
  })

  it("ignores the old confirmed profile during publication of a different cache owner", async () => {
    publishAccount("A")
    await set(accountKey("A"), snapshot("A"))
    // This is the ordering used by applyUserState: the cache owner is published
    // before React's profile state is mirrored to the auth store.
    setQueryCacheIdentity("B")
    expect(await idbPersister.restoreClient()).toBeUndefined()
  })

  it("propagates a storage read failure while the confirmed profile still owns the cache", async () => {
    publishAccount("A")
    await set(accountKey("A"), snapshot("A"))
    const failure = new DOMException("Read transaction aborted", "AbortError")
    io.readError = failure

    await expect(idbPersister.restoreClient()).rejects.toBe(failure)
  })

  it("drops a retired profile before attempting unavailable storage", async () => {
    publishAccount("A")
    await set(accountKey("A"), snapshot("A"))
    setQueryCacheIdentity("B")
    io.readError = new DOMException("Read transaction aborted", "AbortError")

    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
  })
})

describe("asynchronous persistence ownership", () => {
  it("rejects an in-flight restore when only the browser session rotates", async () => {
    publishAccount("A")
    await idbPersister.persistClient(snapshot("A"))
    const read = pause()
    io.afterRead = read.hold
    const restoring = idbPersister.restoreClient()
    try {
      await vi.waitFor(() => expect(read.entered()).toBe(true))
      rotateBrowserSession()
      read.release()
      expect(await restoring).toBeUndefined()
    } finally {
      read.release()
      await Promise.allSettled([restoring])
    }
    io.afterRead = undefined
    // Rotation retires the in-flight operation, not this account's saved data.
    expect(await idbPersister.restoreClient()).toBeDefined()
  })

  it("preserves the new same-account snapshot while an outgoing write retires", async () => {
    publishAccount("A")
    const write = pause()
    io.afterWrite = write.hold
    const outgoing = idbPersister.persistClient(snapshot("A"))
    let successor: ReturnType<typeof idbPersister.persistClient> | undefined
    try {
      await vi.waitFor(() => expect(write.entered()).toBe(true))
      rotateBrowserSession()
      io.afterWrite = undefined
      const saved = snapshot("A")
      const schedule = saved.clientState.queries.find((query) => query.queryKey[0] === "schedule")!
      schedule.state.data = ["new session schedule"]
      successor = idbPersister.persistClient(saved)
      write.release()
      await Promise.all([outgoing, successor])
      expect(await get(accountKey("A"))).toEqual(withoutCurrentUserProfile(saved))
    } finally {
      write.release()
      await Promise.allSettled([outgoing, successor])
    }
  })

  it("drops retired queued writes before attempting unavailable storage", async () => {
    publishAccount("A")
    const write = pause()
    io.afterWrite = write.hold
    const first = idbPersister.persistClient(snapshot("A"))
    let queued: ReturnType<typeof idbPersister.persistClient> | undefined
    try {
      await vi.waitFor(() => expect(write.entered()).toBe(true))
      queued = idbPersister.persistClient(snapshot("A"))
      rotateBrowserSession()
      io.writeError = new Error("IndexedDB write unavailable")
      write.release()
      await expect(Promise.all([first, queued])).resolves.toEqual([undefined, undefined])
      expect(await keys()).toEqual([])
    } finally {
      write.release()
      await Promise.allSettled([first, queued])
    }
    io.writeError = undefined
    io.afterWrite = undefined
    await idbPersister.persistClient(snapshot("A"))
    expect(await get(accountKey("A"))).toBeDefined()
  })

  it("keeps a stale restore retired through an A-to-B-to-A identity transition", async () => {
    publishAccount("A")
    await idbPersister.persistClient(snapshot("A"))
    const read = pause()
    io.afterRead = read.hold
    const restoring = idbPersister.restoreClient()
    try {
      await vi.waitFor(() => expect(read.entered()).toBe(true))
      publishAccount("B")
      publishAccount("A")
      read.release()
      expect(await restoring).toBeUndefined()
    } finally {
      read.release()
      await Promise.allSettled([restoring])
    }
  })

  it("removes the captured account if identity changes while legacy deletion is pending", async () => {
    publishAccount("A")
    await idbPersister.persistClient(snapshot("A"))
    publishAccount("B")
    await idbPersister.persistClient(snapshot("B"))
    publishAccount("A")
    const legacyDeletion = pause()
    io.beforeDelete = async (key) => {
      if (key === "reactQuery") await legacyDeletion.hold()
    }
    const removing = idbPersister.removeClient()
    try {
      await vi.waitFor(() => expect(legacyDeletion.entered()).toBe(true))
      publishAccount("B")
      legacyDeletion.release()
      await removing
      expect(await get(accountKey("A"))).toBeUndefined()
      expect(await get(accountKey("B"))).toBeDefined()
    } finally {
      legacyDeletion.release()
      await Promise.allSettled([removing])
    }
  })

  it.each(["A", "null"])(
    "preserves account %s while removing the legacy snapshot signed out",
    async (owner) => {
      const saved = snapshot(owner)
      await set("reactQuery", saved)
      await set(accountKey(owner), saved)
      await idbPersister.removeClient()
      expect(await keys()).toEqual([accountKey(owner)])
    }
  )
})

describe("request-hydrated cache during auth bootstrap", () => {
  it.each([SSR_STUB_USER_ID, ENCRYPTED_CACHE_PLACEHOLDER_USER_ID, -1])(
    "preserves the current unresolved %s snapshot until sign-out is confirmed",
    (placeholder) => {
      useAuthStore.setState({ user: null, loading: true })
      const active = createQueryClient()
      const key = ["dashboard", "events"] as const
      active.setQueryData(key, ["request-scoped event"])
      try {
        useAuthStore.setState({
          user: { ...testUser, id: placeholder } as unknown as UserState,
          loading: false,
        })
        expect(active.getQueryData(key)).toEqual(["request-scoped event"])

        publishAccount(null)
        expect(active.getQueryData(key)).toBeUndefined()
      } finally {
        active.clear()
      }
    }
  )

  it("preserves only committed null markers while retiring a settled bootstrap", () => {
    useAuthStore.setState({ user: null, loading: true })
    publishAccount(ENCRYPTED_CACHE_PLACEHOLDER_USER_ID)
    const marker = createQueryClient()
    const absent = createQueryClient()
    const stale = createQueryClient()
    const placeholder = createQueryClient()
    const clients = [marker, absent, stale, placeholder]
    const profileKey = ["users", "me"] as const
    const privateKey = ["dashboard", "events"] as const
    marker.setQueryData(profileKey, null)
    stale.setQueryData(profileKey, { ...testUser, id: "retired-owner" })
    placeholder.setQueryData(profileKey, { ...testUser, id: SSR_STUB_USER_ID })
    for (const client of clients) {
      client.setQueryData(privateKey, ["private event"])
      client.getMutationCache().build(client, { mutationKey: ["private", "write"] })
    }
    const ownsPreviousEpoch = captureSessionEpoch()

    try {
      publishAccount(null)
      expect(marker.getQueryData(profileKey)).toBeNull()
      expect(marker.getQueryCache().getAll()).toHaveLength(1)
      for (const client of [absent, stale, placeholder]) {
        expect(client.getQueryData(profileKey)).toBeUndefined()
        expect(client.getQueryCache().getAll()).toHaveLength(0)
      }
      for (const client of clients) {
        expect(client.getQueryData(privateKey)).toBeUndefined()
        expect(client.getMutationCache().getAll()).toHaveLength(0)
      }
      expect(ownsPreviousEpoch()).toBe(false)
    } finally {
      for (const client of clients) client.clear()
    }
  })

  it("prunes dead clients while retiring bootstrap without creating a null marker", () => {
    useAuthStore.setState({ user: null, loading: true })
    publishAccount(SSR_STUB_USER_ID)
    const active = createQueryClient()
    active.setQueryData(["dashboard", "events"], ["request event"])
    const deref = vi.fn(() => undefined)
    vi.stubGlobal(
      "WeakRef",
      class {
        deref = deref
      }
    )
    try {
      createQueryClient()
    } finally {
      vi.unstubAllGlobals()
    }

    try {
      publishAccount(null)
      expect(deref).toHaveBeenCalledTimes(2)
      expect(active.getQueryCache().getAll()).toHaveLength(0)
      setQueryCacheIdentity("next-owner")
      expect(deref).toHaveBeenCalledTimes(2)
    } finally {
      active.clear()
      setQueryCacheIdentity(null)
    }
  })

  it("does not republish a null marker when bootstrap returns a malformed identity", () => {
    useAuthStore.setState({ user: null, loading: true })
    publishAccount(SSR_STUB_USER_ID)
    const active = createQueryClient()
    active.setQueryData(["users", "me"], null)
    try {
      publishAccount("")
      expect(active.getQueryCache().getAll()).toHaveLength(0)
    } finally {
      active.clear()
    }
  })

  it("retires a previous account when a bootstrap placeholder replaces it", () => {
    publishAccount("A")
    const active = createQueryClient()
    const key = ["dashboard", "events"] as const
    active.setQueryData(key, ["private account A event"])
    try {
      publishAccount(SSR_STUB_USER_ID)
      expect(active.getQueryData(key)).toBeUndefined()
    } finally {
      active.clear()
    }
  })

  it("retires the unresolved cache when bootstrap returns a malformed identity", () => {
    useAuthStore.setState({ user: null, loading: true })
    publishAccount(SSR_STUB_USER_ID)
    const active = createQueryClient()
    const key = ["dashboard", "events"] as const
    active.setQueryData(key, ["request-scoped event"])
    try {
      publishAccount("")
      expect(active.getQueryData(key)).toBeUndefined()
    } finally {
      active.clear()
    }
  })

  it("does not preserve a bootstrap cache after the browser generation changes", () => {
    useAuthStore.setState({ user: null, loading: true })
    publishAccount(SSR_STUB_USER_ID)
    const active = createQueryClient()
    const key = ["dashboard", "events"] as const
    active.setQueryData(key, ["retired request event"])
    try {
      localStorage.setItem(
        sessionKey,
        JSON.stringify({ nonce: "successor-generation", hash: null })
      )
      publishAccount(SSR_STUB_USER_ID)
      expect(active.getQueryData(key)).toBeUndefined()
    } finally {
      active.clear()
      acceptBrowserSessionGeneration()
    }
  })

  it("retires request data when an initially empty bootstrap settles signed out", () => {
    useAuthStore.setState({ user: null, loading: true })
    const active = createQueryClient()
    const key = ["dashboard", "events"] as const
    active.setQueryData(key, ["unconfirmed request event"])
    try {
      publishAccount(null)
      expect(active.getQueryData(key)).toBeUndefined()
    } finally {
      active.clear()
    }
  })

  it("retires a malformed bootstrap identity without coercing its id", () => {
    useAuthStore.setState({ user: null, loading: true })
    publishAccount(SSR_STUB_USER_ID)
    const active = createQueryClient()
    const key = ["dashboard", "events"] as const
    active.setQueryData(key, ["request-scoped event"])
    const coerce = vi.fn(() => {
      throw new Error("Malformed identity must not be coerced")
    })
    try {
      useAuthStore.setState({
        user: { ...testUser, id: { toString: coerce } } as unknown as UserState,
        loading: false,
      })
      expect(coerce).not.toHaveBeenCalled()
      expect(active.getQueryData(key)).toBeUndefined()
    } finally {
      active.clear()
    }
  })
})

describe("AUD-472 release-scoped persistence", () => {
  it.each([
    {
      label: "discards a prior release even when the legacy version stays unchanged",
      initialRelease: "release-a",
      nextRelease: "release-b",
      initialVersion: "1.0.0",
      nextVersion: "1.0.0",
      restored: false,
    },
    {
      label: "retains the same release across a reload",
      initialRelease: "release-a",
      nextRelease: "release-a",
      initialVersion: "1.0.0",
      nextVersion: "1.0.0",
      restored: true,
    },
    {
      label: "uses the release rather than an unrelated legacy version change",
      initialRelease: "release-a",
      nextRelease: "release-a",
      initialVersion: "1.0.0",
      nextVersion: "2.0.0",
      restored: true,
    },
    {
      label: "preserves legacy version invalidation when no release is supplied",
      initialRelease: "",
      nextRelease: "",
      initialVersion: "1.0.0",
      nextVersion: "2.0.0",
      restored: false,
    },
    {
      label: "keeps the development fallback stable without either build identifier",
      initialRelease: "",
      nextRelease: "",
      initialVersion: "",
      nextVersion: "",
      restored: true,
    },
  ])("$label", async ({ initialRelease, nextRelease, initialVersion, nextVersion, restored }) => {
    const storageKey = "aud472:release-cache"
    const queryKey = ["aud472", "persisted-release-data"] as const
    const data = { title: "Snapshot from the first build" }
    const clients: ReturnType<typeof createQueryClient>[] = []
    const loadBuild = async (release: string, version: string) => {
      vi.stubEnv("VITE_APP_RELEASE", release)
      vi.stubEnv("VITE_APP_VERSION", version)
      vi.resetModules()
      const build = await import("../queryClient")
      clients.push(build.queryClient)
      return build
    }

    try {
      const first = await loadBuild(initialRelease, initialVersion)
      const source = first.createQueryClient()
      clients.push(source)
      source.setQueryData(queryKey, data)
      await persistQueryClientSave({
        ...first.persistOptions,
        queryClient: source,
        persister: first.createIDBPersister(storageKey),
      })
      const saved = await get<PersistedClient>(storageKey)
      expect(saved?.clientState.queries).toHaveLength(1)
      expect(saved?.clientState.queries[0]?.state.data).toEqual(data)

      const second = await loadBuild(nextRelease, nextVersion)
      const target = second.createQueryClient()
      clients.push(target)
      await persistQueryClientRestore({
        ...second.persistOptions,
        queryClient: target,
        persister: second.createIDBPersister(storageKey),
      })

      if (restored) {
        expect(target.getQueryData(queryKey)).toEqual(data)
        expect(await get<PersistedClient>(storageKey)).toEqual(saved)
      } else {
        expect(target.getQueryData(queryKey)).toBeUndefined()
        expect(target.getQueryCache().getAll()).toEqual([])
        expect(await get<PersistedClient>(storageKey)).toBeUndefined()
      }
    } finally {
      try {
        for (const client of clients) client.clear()
        await del(storageKey)
      } finally {
        vi.unstubAllEnvs()
        vi.resetModules()
      }
    }
  })
})
