import type { AppDatabase } from "./index"

/** Load the IndexedDB implementation only when an offline-capable feature needs it. */
export async function getDatabaseLazily(): Promise<AppDatabase> {
  const { getDatabase } = await import("./index")
  return getDatabase()
}

// Keep document types available to offline-capable hooks without pulling the
// RxDB implementation into their initial module graph.
export type { ScheduleDoc } from "./index"
