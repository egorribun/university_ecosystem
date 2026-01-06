import { openDB, type IDBPDatabase } from "idb";
import { log, warn, error } from "./logger";

const CLICK_DB_NAME = "notification-interactions";
const DB_VERSION = 1;

export const STORES = {
  NAVIGATION: "pending-navigations",
  REPORT: "pending-reports",
  NEWS_INTERACTION: "pending-news-interactions",
} as const;

/**
 * Initialize IndexedDB for offline interaction queue.
 */
export async function initOfflineQueue() {
  await openDB(CLICK_DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORES.NAVIGATION)) {
        db.createObjectStore(STORES.NAVIGATION, { keyPath: "id", autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(STORES.REPORT)) {
        db.createObjectStore(STORES.REPORT, { keyPath: "id", autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(STORES.NEWS_INTERACTION)) {
        db.createObjectStore(STORES.NEWS_INTERACTION, { keyPath: "id", autoIncrement: true });
      }
    },
  });
}

function isOnline(): boolean {
  return self.navigator.onLine !== false;
}

export async function addRecord<T extends object>(storeName: string, value: T) {
  const db = await openDB(CLICK_DB_NAME, DB_VERSION);
  return db.add(storeName, value);
}

export async function processOfflineQueues() {
  if (!isOnline()) return;

  log("Processing offline queues...");
  const db = await openDB(CLICK_DB_NAME, DB_VERSION);

  await Promise.all([
    processNavigationQueue(db),
    processReportQueue(db),
    processNewsInteractionQueue(db),
  ]);
}

async function processNavigationQueue(db: IDBPDatabase) {
  const records = await db.getAll(STORES.NAVIGATION);
  for (const record of records) {
    // Original focusOrOpenClient logic goes here
    log("Processing navigation", record);
    await db.delete(STORES.NAVIGATION, record.id);
  }
}

async function processReportQueue(db: IDBPDatabase) {
  const records = await db.getAll(STORES.REPORT);
  for (const record of records) {
    try {
      const response = await fetch(record.reportUrl, {
        method: "POST",
        body: JSON.stringify(record.payload),
        headers: { "Content-Type": "application/json" },
        keepalive: true,
      });
      if (response.ok) {
        await db.delete(STORES.REPORT, record.id);
      }
    } catch (err) {
      warn("Failed to sync report", err);
      break;
    }
  }
}

async function processNewsInteractionQueue(db: IDBPDatabase) {
  const records = await db.getAll(STORES.NEWS_INTERACTION);
  for (const record of records) {
    try {
      const response = await fetch(record.url, {
        method: "POST",
        body: JSON.stringify(record.payload),
        headers: { "Content-Type": "application/json" },
      });
      if (response.ok) {
        await db.delete(STORES.NEWS_INTERACTION, record.id);
      }
    } catch (err) {
      warn("Failed to sync news interaction", err);
      break;
    }
  }
}
