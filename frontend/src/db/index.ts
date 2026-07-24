import { createRxDatabase, type RxDatabase, addRxPlugin } from "rxdb"
import { getRxStorageDexie } from "rxdb/plugins/storage-dexie"
import { RxDBDevModePlugin } from "rxdb/plugins/dev-mode"
import { wrappedValidateAjvStorage } from "rxdb/plugins/validate-ajv"

import { scheduleSchema, type ScheduleDoc } from "./schemas/schedule"
import { notesSchema, type NoteDoc } from "./schemas/notes"
import { messagesSchema, type MessageDoc } from "./schemas/messages"

if (import.meta.env.DEV) {
  addRxPlugin(RxDBDevModePlugin)
}

export type AppCollections = {
  schedule: any
  notes: any
  messages: any
}

export type AppDatabase = RxDatabase<AppCollections>

let dbPromise: Promise<AppDatabase> | null = null

export async function getDatabase(): Promise<AppDatabase> {
  if (!dbPromise) {
    dbPromise = createRxDatabase<AppCollections>({
      name: "university_ecosystem_rxdb",
      storage: wrappedValidateAjvStorage({ storage: getRxStorageDexie() }),
      ignoreDuplicate: true,
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

export type { ScheduleDoc, NoteDoc, MessageDoc }
