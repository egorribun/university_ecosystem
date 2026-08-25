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
  if (dbPromise) {
    try {
      const db = await dbPromise
      dbPromise = null
      const dbObj = db as unknown as Record<string, unknown>
      if (typeof dbObj["remove"] === "function") {
        await (dbObj["remove"] as () => Promise<void>)()
      } else if (typeof dbObj["close"] === "function") {
        await (dbObj["close"] as () => Promise<void>)()
      }
    } catch (_e) {
      dbPromise = null
    }
  }
}

export type { ScheduleDoc, NoteDoc, MessageDoc }
