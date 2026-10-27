import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { UserState } from "@/types/Auth"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration, rotateBrowserSession } from "@/stores/sessionEpoch"
import LivePushToasts, {
  readBuffer,
  writeBuffer,
  getBufferStorageKey,
  type ActiveToast,
} from "../feedback/LivePushToasts"

const SESSION_GENERATION_KEY = "ecosystem.session.generation.v1"
const TEST_USER_ID = "toast-legacy-test-user"
const BUFFER_STORAGE_KEY = getBufferStorageKey(TEST_USER_ID)

const translations: Record<string, string> = {
  "notifications:defaultTitle": "University Ecosystem",
  "notifications:defaultBody": "Stay informed",
  "notifications:toast.open": "Open",
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => translations[`notifications:${key}`] ?? key,
  }),
}))

const dispatchToast = (toast: Record<string, unknown>) => {
  act(() => {
    const event = new MessageEvent("message", {
      data: {
        type: "PUSH_NOTIFICATION",
        recipientUserId: TEST_USER_ID,
        toast,
      },
    })
    ;(navigator.serviceWorker as EventTarget).dispatchEvent(event)
  })
}

const setVisibilityState = (state: DocumentVisibilityState) => {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => state,
  })
}

describe("LivePushToasts", () => {
  beforeEach(() => {
    setVisibilityState("visible")
    localStorage.clear()
    acceptBrowserSessionGeneration()
    useAuthStore.setState({ user: { id: TEST_USER_ID } as UserState, loading: false })
    Object.defineProperty(window.navigator, "serviceWorker", {
      configurable: true,
      value: new EventTarget(),
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("buffers toasts received while hidden and flushes them when visible", async () => {
    setVisibilityState("hidden")
    render(<LivePushToasts />)

    dispatchToast({ title: "Hidden toast", body: "Will show later" })

    expect(screen.queryByText("Hidden toast")).not.toBeInTheDocument()

    setVisibilityState("visible")
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"))
    })

    expect(await screen.findByText("Hidden toast")).toBeInTheDocument()
    expect(screen.getByText("Will show later")).toBeInTheDocument()
  })

  it("dedupes buffered toasts and caps the buffer size", () => {
    setVisibilityState("hidden")
    render(<LivePushToasts />)

    const duplicateToast = { id: "toast-1", title: "Duplicate", body: "Only once" }
    dispatchToast(duplicateToast)
    dispatchToast(duplicateToast)

    const bufferAfterDupes = JSON.parse(localStorage.getItem(BUFFER_STORAGE_KEY) ?? "[]")
    expect(bufferAfterDupes).toHaveLength(1)

    for (let index = 0; index < 30; index += 1) {
      dispatchToast({ id: `toast-${index}`, title: `Toast ${index}`, body: "Buffered" })
    }

    const bufferedToasts = JSON.parse(localStorage.getItem(BUFFER_STORAGE_KEY) ?? "[]")
    expect(bufferedToasts.length).toBeLessThanOrEqual(20)

    setVisibilityState("visible")
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
    })

    expect(localStorage.getItem(BUFFER_STORAGE_KEY)).toBe("[]")
  })

  it("fails closed when storage exposes neither read nor write capability", () => {
    const nativeStorage = window.localStorage
    const unavailableStorage = { getItem: undefined, setItem: undefined }
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: unavailableStorage,
    })

    try {
      expect(readBuffer()).toEqual([])
      const toast = { id: "storage-less", title: "Title", body: "Body" } as ActiveToast
      expect(() => writeBuffer([toast])).not.toThrow()
      expect(unavailableStorage.getItem).toBeUndefined()
      expect(unavailableStorage.setItem).toBeUndefined()
    } finally {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: nativeStorage,
      })
    }
  })

  it("keeps reading and writing independently when one storage method is unavailable", () => {
    const nativeStorage = window.localStorage
    rotateBrowserSession()
    const generationSnapshot = nativeStorage.getItem(SESSION_GENERATION_KEY)
    expect(generationSnapshot).not.toBeNull()
    const getOnlyStorage = {
      getItem: vi.fn((key: string) =>
        key === SESSION_GENERATION_KEY
          ? generationSnapshot
          : JSON.stringify([{ id: "stored", title: "Stored", body: "Body" }])
      ),
      setItem: undefined,
    }
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: getOnlyStorage,
    })

    try {
      expect(readBuffer().map(({ id }) => id)).toEqual(["stored"])
      expect(() => writeBuffer([])).not.toThrow()
      expect(getOnlyStorage.getItem).toHaveBeenCalledWith(BUFFER_STORAGE_KEY)
    } finally {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: nativeStorage,
      })
    }
  })

  it("does not invoke object-valued buffer methods after validating session ownership", () => {
    const nativeStorage = window.localStorage
    rotateBrowserSession()
    const generationSnapshot = nativeStorage.getItem(SESSION_GENERATION_KEY)
    expect(generationSnapshot).not.toBeNull()

    const positiveRead = [{ id: "positive-read", title: "Stored", body: "Readable" }]
    nativeStorage.setItem(BUFFER_STORAGE_KEY, JSON.stringify(positiveRead))
    expect(readBuffer().map(({ id }) => id)).toEqual(["positive-read"])

    const positiveWrite: ActiveToast = {
      id: "positive-write",
      title: "Writable",
      body: "Owner confirmed",
    }
    writeBuffer([positiveWrite])
    expect(
      JSON.parse(nativeStorage.getItem(BUFFER_STORAGE_KEY) ?? "[]").map(({ id }: ActiveToast) => id)
    ).toEqual(["positive-write"])

    const objectGetItem = { call: vi.fn() }
    let generationRead = false
    let getItemAccesses = 0
    const generationGetter = vi.fn((key: string) => {
      if (key === SESSION_GENERATION_KEY) {
        generationRead = true
        return generationSnapshot
      }
      return null
    })
    const malformedReadStorage = {
      get getItem() {
        getItemAccesses += 1
        return generationRead ? objectGetItem : generationGetter
      },
      setItem: vi.fn(),
    }
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: malformedReadStorage,
    })

    try {
      expect(readBuffer()).toEqual([])
      expect(generationGetter).toHaveBeenCalledWith(SESSION_GENERATION_KEY)
      expect(getItemAccesses).toBe(2)
      expect(objectGetItem.call).not.toHaveBeenCalled()

      const objectSetItem = { call: vi.fn() }
      const writeGenerationGetter = vi.fn((key: string) =>
        key === SESSION_GENERATION_KEY ? generationSnapshot : null
      )
      const malformedWriteStorage = {
        getItem: writeGenerationGetter,
        setItem: objectSetItem,
      }
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: malformedWriteStorage,
      })

      expect(() => writeBuffer([positiveWrite])).not.toThrow()
      expect(writeGenerationGetter).toHaveBeenCalledWith(SESSION_GENERATION_KEY)
      expect(objectSetItem.call).not.toHaveBeenCalled()
    } finally {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: nativeStorage,
      })
    }

    expect(
      JSON.parse(nativeStorage.getItem(BUFFER_STORAGE_KEY) ?? "[]").map(({ id }: ActiveToast) => id)
    ).toEqual(["positive-write"])
  })

  it("does not let storage read or write exceptions escape notification delivery", () => {
    const nativeStorage = window.localStorage
    rotateBrowserSession()
    const generationSnapshot = nativeStorage.getItem(SESSION_GENERATION_KEY)
    expect(generationSnapshot).not.toBeNull()
    const throwingStorage = {
      getItem: vi.fn<Storage["getItem"]>((key) => {
        if (key === SESSION_GENERATION_KEY) return generationSnapshot
        throw new Error("private mode")
      }),
      setItem: vi.fn(() => {
        throw new Error("quota")
      }),
    }
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: throwingStorage,
    })

    try {
      expect(readBuffer()).toEqual([])
      expect(() => writeBuffer([])).not.toThrow()
      // Identity snapshots may read the session-generation key; this asserts the single buffer-key read.
      expect(
        throwingStorage.getItem.mock.calls.filter(([key]) => key === BUFFER_STORAGE_KEY)
      ).toHaveLength(1)
      expect(throwingStorage.setItem).toHaveBeenCalledOnce()
    } finally {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: nativeStorage,
      })
    }
  })
})
