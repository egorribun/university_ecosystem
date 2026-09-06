import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import LivePushToasts, {
  readBuffer,
  writeBuffer,
  type ActiveToast,
} from "../feedback/LivePushToasts"

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

    const bufferAfterDupes = JSON.parse(localStorage.getItem("livePushToastBuffer") ?? "[]")
    expect(bufferAfterDupes).toHaveLength(1)

    for (let index = 0; index < 30; index += 1) {
      dispatchToast({ id: `toast-${index}`, title: `Toast ${index}`, body: "Buffered" })
    }

    const bufferedToasts = JSON.parse(localStorage.getItem("livePushToastBuffer") ?? "[]")
    expect(bufferedToasts.length).toBeLessThanOrEqual(20)

    setVisibilityState("visible")
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
    })

    expect(localStorage.getItem("livePushToastBuffer")).toBe("[]")
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
    const getOnlyStorage = {
      getItem: vi.fn(() => JSON.stringify([{ id: "stored", title: "Stored", body: "Body" }])),
      setItem: undefined,
    }
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: getOnlyStorage,
    })

    try {
      expect(readBuffer().map(({ id }) => id)).toEqual(["stored"])
      expect(() => writeBuffer([])).not.toThrow()
      expect(getOnlyStorage.getItem).toHaveBeenCalledWith("livePushToastBuffer")
    } finally {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: nativeStorage,
      })
    }
  })

  it("does not let storage read or write exceptions escape notification delivery", () => {
    const nativeStorage = window.localStorage
    const throwingStorage = {
      getItem: vi.fn(() => {
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
      expect(throwingStorage.getItem).toHaveBeenCalledOnce()
      expect(throwingStorage.setItem).toHaveBeenCalledOnce()
    } finally {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: nativeStorage,
      })
    }
  })
})
