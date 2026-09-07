import { createRxDatabase, type RxDatabase, addRxPlugin } from "rxdb"
import { getRxStorageDexie } from "rxdb/plugins/storage-dexie"
import { RxDBDevModePlugin } from "rxdb/plugins/dev-mode"
import { wrappedValidateAjvStorage } from "rxdb/plugins/validate-ajv"

import { scheduleSchema, type ScheduleDoc } from "./schemas/schedule"
import { notesSchema, type NoteDoc } from "./schemas/notes"
import { messagesSchema, type MessageDoc } from "./schemas/messages"

if (import.meta.env.DEV && import.meta.env.MODE !== "test") {
  addRxPlugin(RxDBDevModePlugin)
}

import type { RxCollection } from "rxdb"

export type AppCollections = {
  schedule: RxCollection<ScheduleDoc>
  notes: RxCollection<NoteDoc>
  messages: RxCollection<MessageDoc>
}

export type AppDatabase = RxDatabase<AppCollections>

let dbPromise: Promise<AppDatabase> | null = null

export async function getDatabase(): Promise<AppDatabase> {
  if (!dbPromise) {
    dbPromise = createRxDatabase<AppCollections>({
      name: "university_ecosystem_rxdb",
      storage: wrappedValidateAjvStorage({ storage: getRxStorageDexie() }),
    }).then(async (db) => {
      await db.addCollections({
        schedule: { schema: scheduleSchema },
        notes: { schema: notesSchema },
        messages: { schema: messagesSchema },
      })
      return db
    })
  }
  return dbPromise
}

export async function resetDatabaseForTesting(): Promise<void> {
  // Keep the reset operation total even when initialization has not started or
  // the previous attempt rejected.  Resolving a null sentinel avoids a second
  // branch that could accidentally touch a rejected promise.
  const pending = dbPromise ?? Promise.resolve(null)
  const db = await pending.catch(() => null)
  if (db === null) {
    dbPromise = null
    return
  }

  // Await initialization before cleanup, then clear the cache regardless of
  // whether the underlying remove/close operation succeeds so a later test
  // can create a fresh database instead of reusing a half-cleaned instance.
  const dbObj = db as unknown as Record<string, unknown>
  const cleanup = (["remove", "close"] as const)
    .map((method) => dbObj[method])
    .find((candidate): candidate is () => Promise<void> => typeof candidate === "function")
  try {
    if (cleanup) await cleanup()
    dbPromise = null
  } catch (_e) {
    dbPromise = null
  }
}

export type { ScheduleDoc, NoteDoc, MessageDoc }
