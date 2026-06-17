import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { SyncStatus } from "@/components/feedback/SyncStatus"

const CLICK_DB_NAME = "notification-interactions"
const CLICK_DB_VERSION = 3
const NEWS_INTERACTION_STORE = "pending-news-interactions"

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value })
}

/** Flush the queued IDB async work (DB open + count) and the component re-render. */
async function flushQueue() {
  await act(async () => {
    // Let the immediate checkQueue() promise chain (open → count) settle, then
    // give React a tick to apply the resulting setPendingCount.
    await Promise.resolve()
    await new Promise((r) => setTimeout(r, 0))
    await Promise.resolve()
  })
}

/** Seed the news-interaction store so checkQueue counts > 0. */
async function seedPendingInteractions(rows: number) {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.open(CLICK_DB_NAME, CLICK_DB_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(NEWS_INTERACTION_STORE)) {
        database.createObjectStore(NEWS_INTERACTION_STORE, { keyPath: "id", autoIncrement: true })
      }
    }
    request.onsuccess = () => {
      const db = request.result
      if (rows === 0) {
        db.close()
        resolve()
        return
      }
      const tx = db.transaction(NEWS_INTERACTION_STORE, "readwrite")
      const store = tx.objectStore(NEWS_INTERACTION_STORE)
      for (let i = 0; i < rows; i++) store.add({ payload: `pending-${i}` })
      tx.oncomplete = () => {
        db.close()
        resolve()
      }
      tx.onerror = () => reject(tx.error)
    }
    request.onerror = () => reject(request.error)
  })
}

async function deleteDb() {
  await new Promise<void>((resolve) => {
    const req = indexedDB.deleteDatabase(CLICK_DB_NAME)
    req.onsuccess = () => resolve()
    req.onerror = () => resolve()
    req.onblocked = () => resolve()
  })
}

describe("SyncStatus", () => {
  beforeEach(() => {
    setOnline(true)
  })

  afterEach(async () => {
    // Restore real timers FIRST — fake-indexeddb drives its own async scheduler
    // off real microtasks/timers, so deleteDb() would hang under fake timers.
    vi.useRealTimers()
    setOnline(true)
    await deleteDb()
  })

  it("renders the online status badge when online (Cloud icon, no count)", async () => {
    setOnline(true)
    render(<SyncStatus />)
    await flushQueue()

    const status = screen.getByRole("status")
    expect(status).toBeInTheDocument()
    expect(status).toHaveAttribute("title", "common:sync.online")
    // No pending count badge when the queue is empty.
    expect(screen.queryByText("0")).not.toBeInTheDocument()
  })

  it("renders nothing when offline with an empty queue", async () => {
    setOnline(false)
    render(<SyncStatus />)
    await flushQueue()

    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("renders the offline badge with a pending count when offline + queued items", async () => {
    await seedPendingInteractions(3)
    setOnline(false)
    render(<SyncStatus />)
    await flushQueue()

    const status = screen.getByRole("status")
    expect(status).toBeInTheDocument()
    expect(status).toHaveAttribute("title", "common:sync.offline")
    expect(screen.getByText("3")).toBeInTheDocument()
  })

  it("renders the online badge with a pending count when online + queued items", async () => {
    await seedPendingInteractions(2)
    setOnline(true)
    render(<SyncStatus />)
    await flushQueue()

    const status = screen.getByRole("status")
    expect(status).toHaveAttribute("title", "common:sync.online")
    expect(screen.getByText("2")).toBeInTheDocument()
  })

  it("re-evaluates the queue on the 3s interval and reflects newly-seeded items", async () => {
    // Real timers: fake-indexeddb runs its async work off real microtasks/timers,
    // which vi.advanceTimersByTimeAsync does not drive reliably.
    setOnline(true)
    render(<SyncStatus />)
    await flushQueue()
    // Initial empty queue → online badge, no count.
    expect(screen.getByRole("status")).toHaveAttribute("title", "common:sync.online")
    expect(screen.queryByText("1")).not.toBeInTheDocument()

    // Seed an item, then wait past the 3s interval for the scheduled re-check.
    await seedPendingInteractions(1)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 3200))
    })

    expect(screen.getByText("1")).toBeInTheDocument()
  }, 10000)

  it("reacts to the window offline event (hides when the queue is empty)", async () => {
    setOnline(true)
    render(<SyncStatus />)
    await flushQueue()
    expect(screen.getByRole("status")).toBeInTheDocument()

    await act(async () => {
      setOnline(false)
      window.dispatchEvent(new Event("offline"))
      await Promise.resolve()
    })

    // Offline + empty queue → component returns null (exercises the offline
    // listener wiring + the early-return branch via a runtime state transition).
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
