import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { addRxPlugin, createRxDatabase, getRxStorageDexie, wrappedValidateAjvStorage } = vi.hoisted(
  () => ({
    addRxPlugin: vi.fn(),
    createRxDatabase: vi.fn(),
    getRxStorageDexie: vi.fn(() => "dexie-storage"),
    wrappedValidateAjvStorage: vi.fn(({ storage }: { storage: unknown }) => ({
      storage,
    })),
  })
)

vi.mock("rxdb", () => ({
  addRxPlugin,
  createRxDatabase,
}))
vi.mock("rxdb/plugins/dev-mode", () => ({ RxDBDevModePlugin: "dev-mode-plugin" }))
vi.mock("rxdb/plugins/storage-dexie", () => ({ getRxStorageDexie }))
vi.mock("rxdb/plugins/validate-ajv", () => ({ wrappedValidateAjvStorage }))

let getDatabase: typeof import("../index").getDatabase
let resetDatabaseForTesting: typeof import("../index").resetDatabaseForTesting

const makeDatabase = (overrides: Record<string, unknown> = {}) => ({
  addCollections: vi.fn().mockResolvedValue(undefined),
  ...overrides,
})

beforeEach(async () => {
  vi.resetModules()
  const databaseModule = await import("../index")
  getDatabase = databaseModule.getDatabase
  resetDatabaseForTesting = databaseModule.resetDatabaseForTesting
  await resetDatabaseForTesting()
  vi.clearAllMocks()
})

afterEach(async () => {
  await resetDatabaseForTesting()
})

describe("RxDB database lifecycle", () => {
  it("treats an empty cache as an idempotent reset", async () => {
    await expect(resetDatabaseForTesting()).resolves.toBeUndefined()
    expect(createRxDatabase).not.toHaveBeenCalled()
  })

  it("does not register the noisy development plugin in the test runtime", async () => {
    vi.stubEnv("DEV", true)
    vi.stubEnv("MODE", "test")
    vi.resetModules()
    addRxPlugin.mockClear()

    try {
      await import("../index")
      expect(addRxPlugin).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it("registers the development plugin for an actual development build", async () => {
    vi.stubEnv("DEV", true)
    vi.stubEnv("MODE", "development")
    vi.resetModules()
    addRxPlugin.mockClear()

    try {
      await import("../index")
      expect(addRxPlugin).toHaveBeenCalledWith("dev-mode-plugin")
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it("does not register the development plugin in production", async () => {
    vi.stubEnv("DEV", false)
    vi.resetModules()
    addRxPlugin.mockClear()

    try {
      await import("../index")
      expect(addRxPlugin).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it("creates the validated database once and opens the Dexie collections", async () => {
    const database = makeDatabase()
    createRxDatabase.mockResolvedValue(database)

    const first = await getDatabase()
    const second = await getDatabase()

    expect(first).toBe(database)
    expect(second).toBe(database)
    expect(createRxDatabase).toHaveBeenCalledOnce()
    expect(createRxDatabase).toHaveBeenCalledWith({
      name: "university_ecosystem_rxdb",
      storage: { storage: "dexie-storage" },
    })
    expect(getRxStorageDexie).toHaveBeenCalledOnce()
    expect(wrappedValidateAjvStorage).toHaveBeenCalledWith({ storage: "dexie-storage" })
    expect(database.addCollections).toHaveBeenCalledOnce()
    expect(database.addCollections).toHaveBeenCalledWith({
      schedule: expect.objectContaining({ schema: expect.any(Object) }),
      notes: expect.objectContaining({ schema: expect.any(Object) }),
      messages: expect.objectContaining({ schema: expect.any(Object) }),
    })
  })

  it("removes a database when the testing double exposes remove", async () => {
    const remove = vi.fn().mockResolvedValue(undefined)
    const database = makeDatabase({ remove })
    createRxDatabase.mockResolvedValue(database)

    await getDatabase()
    await resetDatabaseForTesting()

    expect(remove).toHaveBeenCalledOnce()
  })

  it("closes a database when remove is unavailable", async () => {
    const close = vi.fn().mockResolvedValue(undefined)
    const database = makeDatabase({ close })
    createRxDatabase.mockResolvedValue(database)

    await getDatabase()
    await resetDatabaseForTesting()

    expect(close).toHaveBeenCalledOnce()
  })

  it("clears the cache when a database exposes no cleanup method", async () => {
    const database = makeDatabase()
    createRxDatabase.mockResolvedValue(database)

    await getDatabase()
    await expect(resetDatabaseForTesting()).resolves.toBeUndefined()

    const replacement = makeDatabase()
    createRxDatabase.mockResolvedValueOnce(replacement)
    await expect(getDatabase()).resolves.toBe(replacement)
  })

  it("clears the cached promise when cleanup rejects", async () => {
    const remove = vi.fn().mockRejectedValue(new Error("cleanup failed"))
    const database = makeDatabase({ remove })
    createRxDatabase.mockResolvedValue(database)

    await getDatabase()
    await expect(resetDatabaseForTesting()).resolves.toBeUndefined()
    expect(remove).toHaveBeenCalledOnce()

    const replacement = makeDatabase()
    createRxDatabase.mockResolvedValueOnce(replacement)
    await expect(getDatabase()).resolves.toBe(replacement)
  })

  it("clears the cached promise when database initialization rejects", async () => {
    createRxDatabase.mockRejectedValueOnce(new Error("initialization failed"))

    await expect(getDatabase()).rejects.toThrow("initialization failed")
    await expect(resetDatabaseForTesting()).resolves.toBeUndefined()

    const replacement = makeDatabase()
    createRxDatabase.mockResolvedValueOnce(replacement)
    await expect(getDatabase()).resolves.toBe(replacement)
  })
})

function deferredDatabaseOperation<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function expectOriginalInitializationError(
  results: PromiseSettledResult<unknown>[],
  error: Error
) {
  for (const result of results) {
    expect(result.status).toBe("rejected")
    if (result.status === "rejected") {
      expect(result.reason).toBe(error)
    }
  }
}

function trackDatabaseCalls() {
  const calls: ReturnType<typeof getDatabase>[] = []
  return {
    request() {
      const call = getDatabase()
      calls.push(call)
      return call
    },
    settle() {
      return Promise.allSettled(calls)
    },
  }
}

describe("AUD-102 production initialization recovery", () => {
  it("shares a failed creation and caches a later successful retry", async () => {
    createRxDatabase.mockReset()
    const creation = deferredDatabaseOperation<ReturnType<typeof makeDatabase>>()
    const originalError = new Error("temporary database creation failure")
    const replacement = makeDatabase()
    const calls = trackDatabaseCalls()

    createRxDatabase.mockReturnValueOnce(creation.promise).mockResolvedValueOnce(replacement)

    const failedCallers = Promise.allSettled([calls.request(), calls.request()])

    try {
      expect(createRxDatabase).toHaveBeenCalledOnce()
      creation.reject(originalError)
      expectOriginalInitializationError(await failedCallers, originalError)

      const recovered = await Promise.all([calls.request(), calls.request()])
      expect(recovered[0]).toBe(replacement)
      expect(recovered[1]).toBe(replacement)
      expect(createRxDatabase).toHaveBeenCalledTimes(2)
      expect(replacement.addCollections).toHaveBeenCalledOnce()
      await expect(calls.request()).resolves.toBe(replacement)
      expect(createRxDatabase).toHaveBeenCalledTimes(2)
    } finally {
      creation.reject(originalError)
      await Promise.allSettled([creation.promise])
      await failedCallers
      await calls.settle()
    }
  })

  it("waits for nondestructive close before permitting another creation", async () => {
    createRxDatabase.mockReset()
    const originalError = new Error("collection registration failed")
    const closeStarted = deferredDatabaseOperation<void>()
    const closeRelease = deferredDatabaseOperation<boolean>()
    const calls = trackDatabaseCalls()
    let closeFinished = false
    let observeLateCaller = Promise.resolve()
    const remove = vi.fn()
    const close = vi.fn(async () => {
      closeStarted.resolve(undefined)
      await closeRelease.promise
      closeFinished = true
      return true
    })
    const database = makeDatabase({
      addCollections: vi.fn().mockRejectedValue(originalError),
      close,
      remove,
    })
    const replacement = makeDatabase()

    createRxDatabase
      .mockResolvedValueOnce(database)
      .mockImplementationOnce(async () => {
        expect(closeFinished).toBe(true)
        return replacement
      })

    const initialCallers = Promise.allSettled([calls.request(), calls.request()])

    try {
      // Defective source rejects without starting close, so this cannot hang.
      await Promise.race([closeStarted.promise, initialCallers])
      expect(close).toHaveBeenCalledOnce()
      expect(remove).not.toHaveBeenCalled()
      expect(createRxDatabase).toHaveBeenCalledOnce()

      let lateCallerSettled = false
      const lateCaller = calls.request()
      observeLateCaller = lateCaller.then(
        () => {
          lateCallerSettled = true
        },
        () => {
          lateCallerSettled = true
        }
      )
      await Promise.resolve()
      await Promise.resolve()

      expect(lateCallerSettled).toBe(false)
      expect(createRxDatabase).toHaveBeenCalledOnce()
      expect(closeFinished).toBe(false)

      closeRelease.resolve(true)
      expectOriginalInitializationError(await initialCallers, originalError)
      await expect(lateCaller).rejects.toBe(originalError)
      expect(closeFinished).toBe(true)
      expect(database.addCollections).toHaveBeenCalledOnce()
      expect(close).toHaveBeenCalledOnce()
      expect(remove).not.toHaveBeenCalled()

      const recovered = await Promise.all([calls.request(), calls.request()])
      expect(recovered[0]).toBe(replacement)
      expect(recovered[1]).toBe(replacement)
      expect(createRxDatabase).toHaveBeenCalledTimes(2)
      expect(replacement.addCollections).toHaveBeenCalledOnce()
      await expect(calls.request()).resolves.toBe(replacement)
      expect(createRxDatabase).toHaveBeenCalledTimes(2)
    } finally {
      closeRelease.resolve(true)
      closeStarted.resolve(undefined)
      await Promise.all([closeRelease.promise, closeStarted.promise])
      await initialCallers
      await calls.settle()
      await observeLateCaller
    }
  })

  it.each(["reject", "throw"] as const)(
    "fails closed with the original error when cleanup must %s",
    async (failureMode) => {
      createRxDatabase.mockReset()
      const originalError = new Error("collection registration failed")
      const cleanupError = new Error("database close failed")
      const calls = trackDatabaseCalls()
      const remove = vi.fn()
      const close = vi.fn(() => {
        if (failureMode === "throw") throw cleanupError
        return Promise.reject(cleanupError)
      })
      const database = makeDatabase({
        addCollections: vi.fn().mockRejectedValue(originalError),
        close,
        remove,
      })
      const unusedReplacement = makeDatabase()

      createRxDatabase
        .mockResolvedValueOnce(database)
        .mockResolvedValueOnce(unusedReplacement)

      try {
        const firstCallers = await Promise.allSettled([calls.request(), calls.request()])
        expectOriginalInitializationError(firstCallers, originalError)
        expect(close).toHaveBeenCalledOnce()

        const laterCallers = await Promise.allSettled([calls.request(), calls.request()])
        expectOriginalInitializationError(laterCallers, originalError)
        expect(createRxDatabase).toHaveBeenCalledOnce()
        expect(database.addCollections).toHaveBeenCalledOnce()
        expect(close).toHaveBeenCalledOnce()
        expect(remove).not.toHaveBeenCalled()
        expect(unusedReplacement.addCollections).not.toHaveBeenCalled()
      } finally {
        await calls.settle()
      }
    }
  )
})
