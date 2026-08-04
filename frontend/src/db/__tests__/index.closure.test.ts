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
  it("creates the validated database once and adds all application collections", async () => {
    const database = makeDatabase()
    createRxDatabase.mockResolvedValue(database)

    const first = await getDatabase()
    const second = await getDatabase()

    expect(first).toBe(database)
    expect(second).toBe(database)
    expect(createRxDatabase).toHaveBeenCalledOnce()
    expect(getRxStorageDexie).toHaveBeenCalledOnce()
    expect(wrappedValidateAjvStorage).toHaveBeenCalledWith({ storage: "dexie-storage" })
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
})
