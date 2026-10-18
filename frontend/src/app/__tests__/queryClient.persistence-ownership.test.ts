import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { dehydrate, hydrate, type QueryKey } from "@tanstack/react-query"
import type { PersistedClient } from "@tanstack/react-query-persist-client"
import { clear, del, get, keys, set } from "idb-keyval"
import {
  acceptBrowserSessionGeneration,
  captureSessionEpoch,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { ENCRYPTED_CACHE_PLACEHOLDER_USER_ID, SSR_STUB_USER_ID } from "@/stores/authIdentity"
import { testUser } from "@/tests/mocks/handlers"

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
        clientState: { ...valid.clientState, queries: [null, ...valid.clientState.queries] },
      },
      { ...valid, clientState: { ...valid.clientState, mutations: null } },
      {
        ...valid,
        clientState: { ...valid.clientState, mutations: [null, ...valid.clientState.mutations] },
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
        clientState: { ...valid.clientState, mutations: [{ state: {}, meta: [] }] },
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
    const inclusiveSnapshot = dehydrate(source, { shouldDehydrateQuery: () => true })
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
  it.each([SSR_STUB_USER_ID, ENCRYPTED_CACHE_PLACEHOLDER_USER_ID])(
    "preserves the current unresolved %s snapshot until sign-out is confirmed",
    (placeholder) => {
      useAuthStore.setState({ user: null, loading: true })
      const active = createQueryClient()
      const key = ["dashboard", "events"] as const
      active.setQueryData(key, ["request-scoped event"])
      try {
        publishAccount(placeholder)
        expect(active.getQueryData(key)).toEqual(["request-scoped event"])

        publishAccount(null)
        expect(active.getQueryData(key)).toBeUndefined()
      } finally {
        active.clear()
      }
    }
  )

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
})
