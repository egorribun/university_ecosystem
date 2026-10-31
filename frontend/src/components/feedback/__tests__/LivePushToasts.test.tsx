import { act, render, screen, fireEvent } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { UserState } from "@/types/Auth"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { getCurrentPushIdentitySnapshot } from "@/push/pushMessageBus"

type CapturedMotionProps = Record<string, unknown> & { children?: unknown }

const motionCapture = vi.hoisted(() => ({
  divProps: [] as CapturedMotionProps[],
  presenceMounts: 0,
  presenceUnmounts: 0,
}))

vi.mock("framer-motion", async () => {
  const React = await import("react")
  const base = (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
  const motion = new Proxy(base.m, {
    get(target, key, receiver) {
      const component = Reflect.get(target, key, receiver)
      if (key !== "div" || typeof component !== "function") return component
      return (props: CapturedMotionProps) => {
        motionCapture.divProps.push(props)
        return component(props)
      }
    },
  })
  const PresenceProbe = ({ children }: { children?: import("react").ReactNode }) => {
    React.useEffect(() => {
      motionCapture.presenceMounts += 1
      return () => {
        motionCapture.presenceUnmounts += 1
      }
    }, [])
    return React.createElement(base.AnimatePresence, null, children)
  }
  return { ...base, AnimatePresence: PresenceProbe, m: motion, motion }
})
const translationState = vi.hoisted(() => ({
  emptySync: false,
  namespaces: [] as unknown[],
}))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationState.namespaces = Array.isArray(namespaces) ? [...namespaces] : [namespaces]
    const emptySync = translationState.emptySync
    return {
      t: (key: string) => (emptySync && key.startsWith("notifications:sync.") ? "" : key),
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))

import LivePushToasts, {
  type ActiveToast,
  bufferToast,
  buildToastId,
  consumeBufferedToasts,
  getBufferStorageKey,
  getDefaultSeverity,
  getToastStorage,
  getToastWindowFeatures,
  getToastWindowTarget,
  getDocumentVisibility,
  getServerVisibility,
  getStableSnapshot,
  hasCloseTimer,
  isSeverityData,
  isSyncCompleteMessage,
  isToastPayload,
  readBuffer,
  rememberToastId,
  resolveSeverity,
  resolveToastActionUrl,
  performToastAction,
  resolveToastContent,
  sanitizeBuffer,
  shouldBufferPush,
  shouldFlushBufferedToasts,
  shouldRenderToast,
  clearCloseTimer,
  createToastEnqueueCallback,
  getToastProgressTransition,
  toActiveToast,
  writeBuffer,
} from "@/components/feedback/LivePushToasts"

const TEST_USER_A_ID = "toast-user-a"
const TEST_USER_B_ID = "toast-user-b"
const TEST_USER_A_BUFFER_KEY = "livePushToastBuffer:toast-user-a"
const TEST_USER_B_BUFFER_KEY = "livePushToastBuffer:toast-user-b"
const SESSION_GENERATION_KEY = "ecosystem.session.generation.v1"
const BUFFER_STORAGE_KEY = getBufferStorageKey(TEST_USER_A_ID)

type SwMessageHandler = (event: MessageEvent) => void

let messageHandler: SwMessageHandler | null = null

/** Install a fake navigator.serviceWorker that captures the message handler. */
function installFakeServiceWorker() {
  messageHandler = null
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      addEventListener: (type: string, handler: SwMessageHandler) => {
        if (type === "message") messageHandler = handler
      },
      removeEventListener: (type: string, handler: SwMessageHandler) => {
        if (type === "message" && messageHandler === handler) messageHandler = null
      },
    },
  })
}

/** Dispatch a service-worker message through the captured handler. */
async function dispatchSwMessage(data: unknown) {
  const currentUserId = useAuthStore.getState().user?.id
  const stampedData =
    data &&
    typeof data === "object" &&
    (data as { type?: unknown }).type === "PUSH_NOTIFICATION" &&
    !("recipientUserId" in data)
      ? { ...data, recipientUserId: currentUserId }
      : data
  await act(async () => {
    messageHandler?.({ data: stampedData } as MessageEvent)
    await Promise.resolve()
  })
}

describe("LivePushToasts", () => {
  beforeEach(() => {
    translationState.emptySync = false
    translationState.namespaces = []
    motionCapture.divProps.length = 0
    motionCapture.presenceMounts = 0
    motionCapture.presenceUnmounts = 0
    window.localStorage.clear()
    useAuthStore.setState({ user: { id: TEST_USER_A_ID } as UserState, loading: false })
    installFakeServiceWorker()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    window.localStorage.clear()
  })

  it("enforces pure routing, storage, rendering, and action contracts", () => {
    expect(getDocumentVisibility()).toBe(document.visibilityState)
    expect(getServerVisibility()).toBe("visible")
    expect(getStableSnapshot()).toBeNull()
    expect(getDefaultSeverity()).toBe("info")
    expect(getBufferStorageKey(TEST_USER_A_ID)).toBe(TEST_USER_A_BUFFER_KEY)
    expect(isSeverityData(null)).toBe(false)
    expect(isSeverityData(undefined)).toBe(false)
    expect(isSeverityData("metadata")).toBe(false)
    expect(isSeverityData([])).toBe(false)
    expect(isSeverityData({ severity: "success" })).toBe(true)
    expect(isToastPayload(null)).toBe(false)
    expect(isToastPayload([])).toBe(false)
    expect(isToastPayload("payload")).toBe(false)
    expect(isToastPayload({ title: "Title" })).toBe(true)

    expect(shouldBufferPush("hidden", false)).toBe(true)
    expect(shouldBufferPush("visible", false)).toBe(false)
    expect(shouldBufferPush("hidden", true)).toBe(false)
    expect(shouldFlushBufferedToasts("visible")).toBe(true)
    expect(shouldFlushBufferedToasts("hidden")).toBe(false)
    expect(isSyncCompleteMessage("SYNC_COMPLETE")).toBe(true)
    expect(isSyncCompleteMessage("PUSH_NOTIFICATION")).toBe(false)
    expect(isSyncCompleteMessage(undefined)).toBe(false)

    const timer = setTimeout(() => undefined, 1)
    expect(hasCloseTimer(timer)).toBe(true)
    expect(hasCloseTimer(null)).toBe(false)
    const clearSpy = vi.spyOn(globalThis, "clearTimeout")
    clearCloseTimer(null)
    expect(clearSpy).not.toHaveBeenCalled()
    clearCloseTimer(timer)
    expect(clearSpy).toHaveBeenCalledWith(timer)
    clearSpy.mockRestore()
    clearTimeout(timer)
    expect(getToastProgressTransition()).toEqual({ duration: 6, ease: "linear" })

    const current: ActiveToast = { id: "content", title: "  Title ", body: "  Body " }
    expect(shouldRenderToast(true, current)).toBe(true)
    expect(shouldRenderToast(false, current)).toBe(false)
    expect(shouldRenderToast(true, null)).toBe(false)
    const translate = vi.fn((key: string) => key)
    expect(resolveToastContent(current, translate)).toEqual({ title: "Title", body: "Body" })
    expect(resolveToastContent(null, translate)).toEqual({
      title: "notifications:defaultTitle",
      body: "notifications:defaultBody",
    })
    expect(resolveToastActionUrl(null)).toBeUndefined()
    expect(resolveToastActionUrl({ id: "action", url: "/events/42" })).toBe("/events/42")
    expect(getToastWindowTarget(true)).toBe("_self")
    expect(getToastWindowTarget(false)).toBe("_blank")
    expect(getToastWindowFeatures(true)).toBeUndefined()
    expect(getToastWindowFeatures(false)).toBe("noopener,noreferrer")
    expect(getToastStorage()).toBe(window.localStorage)
  })

  it("rejects enqueue callbacks stamped with an earlier auth revision", () => {
    const previousIdentity = getCurrentPushIdentitySnapshot()
    expect(previousIdentity.userId).toBe(TEST_USER_A_ID)

    const seenIds = new Set<string>()
    const appended: Array<{ toast: ActiveToast; ownerId: string; ownerRevision: number }> = []
    const enqueue = createToastEnqueueCallback({ current: seenIds }, (entry) => {
      appended.push(entry)
    })

    act(() => {
      useAuthStore.setState({ user: null, loading: false })
      useAuthStore.setState({
        user: {
          id: TEST_USER_A_ID,
          email: "toast-user-a@example.test",
          is_active: true,
        },
        loading: false,
      })
    })

    const currentIdentity = getCurrentPushIdentitySnapshot()
    expect(currentIdentity.userId).toBe(TEST_USER_A_ID)
    expect(currentIdentity.revision).not.toBe(previousIdentity.revision)

    const toast: ActiveToast = { id: "stale-revision", title: "Current session", body: "Toast" }
    enqueue(toast, TEST_USER_A_ID, previousIdentity.revision)
    expect(seenIds.has(toast.id)).toBe(false)
    expect(appended).toEqual([])

    enqueue(toast, TEST_USER_A_ID, currentIdentity.revision)
    expect(seenIds.has(toast.id)).toBe(true)
    expect(appended).toEqual([
      { toast, ownerId: TEST_USER_A_ID, ownerRevision: currentIdentity.revision },
    ])
  })

  it("ignores an action callback after the active toast has been cleared", () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
    const onClose = vi.fn()

    expect(() => performToastAction(null, onClose)).not.toThrow()
    expect(openSpy).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()

    openSpy.mockRestore()
  })

  it("keeps the pure payload boundary fail-closed for every supported shape", () => {
    expect(toActiveToast(null)).toBeNull()
    expect(toActiveToast([])).toBeNull()
    expect(toActiveToast("payload")).toBeNull()
    expect(toActiveToast({ title: " ", body: "\n" })).toBeNull()

    const normalized = toActiveToast({
      id: "  canonical  ",
      title: "  Title  ",
      body: "  Body  ",
      url: "https://example.com/path",
    })
    expect(normalized).toMatchObject({
      id: "canonical",
      title: "Title",
      body: "Body",
      url: "https://example.com/path",
    })
    expect(
      toActiveToast({ id: "unsafe", title: "Unsafe", body: "URL", url: "javascript:1" })
    ).toMatchObject({ id: "unsafe", url: undefined })
  })

  it("resolves severity only from the four canonical string values", () => {
    expect(resolveSeverity(null)).toBe("info")
    expect(resolveSeverity({ id: "missing", title: "x", body: "x" })).toBe("info")
    expect(
      resolveSeverity({ id: "null", title: "x", body: "x", data: null } as unknown as ActiveToast)
    ).toBe("info")
    expect(
      resolveSeverity({ id: "array", title: "x", body: "x", data: [] } as unknown as ActiveToast)
    ).toBe("info")
    expect(resolveSeverity({ id: "number", title: "x", body: "x", data: { severity: 1 } })).toBe(
      "info"
    )
    expect(
      resolveSeverity({ id: "unknown", title: "x", body: "x", data: { severity: "other" } })
    ).toBe("info")
    expect(
      resolveSeverity({ id: "success", title: "x", body: "x", data: { severity: " SUCCESS " } })
    ).toBe("success")
    expect(
      resolveSeverity({ id: "warning", title: "x", body: "x", data: { severity: "warning" } })
    ).toBe("warning")
    expect(
      resolveSeverity({ id: "error", title: "x", body: "x", data: { severity: "error" } })
    ).toBe("error")
  })

  it("selects deterministic toast identities before generating a fallback", () => {
    expect(buildToastId({ id: "  id  ", tag: "tag", timestamp: 1 })).toBe("id")
    expect(buildToastId({ tag: "  tag  ", timestamp: 1 })).toBe("tag")
    expect(buildToastId({ timestamp: 0 })).toBe("0")

    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0.5)
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(42)
    expect(buildToastId({ timestamp: Number.NaN })).toBe("42-i")
    expect(buildToastId({ timestamp: Number.POSITIVE_INFINITY })).toBe("42-i")
    randomSpy.mockRestore()
    nowSpy.mockRestore()
  })

  it("sanitizes persisted buffers and maintains bounded storage semantics", () => {
    expect(sanitizeBuffer(null)).toEqual([])
    expect(sanitizeBuffer({})).toEqual([])
    expect(sanitizeBuffer([null, 1, [], { title: "" }])).toEqual([])
    expect(sanitizeBuffer([{ id: "valid", title: "Valid", body: "Toast" }])).toMatchObject([
      { id: "valid", title: "Valid", body: "Toast" },
    ])

    const valid = (id: string): ActiveToast => ({ id, title: id, body: "body" })
    writeBuffer(Array.from({ length: 25 }, (_, index) => valid(`buffer-${index}`)))
    const persisted = readBuffer()
    expect(persisted).toHaveLength(20)
    expect(persisted[0]?.id).toBe("buffer-5")
    expect(persisted.at(-1)?.id).toBe("buffer-24")
    expect(consumeBufferedToasts()).toHaveLength(20)
    expect(readBuffer()).toEqual([])

    const buffered = valid("buffered")
    bufferToast(buffered)
    bufferToast({ ...buffered, body: "updated" })
    expect(readBuffer()).toEqual([{ ...buffered, body: "updated" }])
  })

  it("does not parse an empty persisted value or write when consuming an empty buffer", () => {
    window.localStorage.setItem(BUFFER_STORAGE_KEY, "")
    const parseSpy = vi.spyOn(JSON, "parse")
    expect(readBuffer()).toEqual([])
    expect(parseSpy).not.toHaveBeenCalled()
    parseSpy.mockRestore()

    window.localStorage.clear()
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")
    expect(consumeBufferedToasts()).toEqual([])
    expect(setItemSpy).not.toHaveBeenCalled()
    setItemSpy.mockRestore()
  })

  it("keeps storage helpers safe when invoked during SSR", () => {
    const browserWindow = globalThis.window
    vi.stubGlobal("window", undefined)
    try {
      expect(readBuffer()).toEqual([])
      expect(() => writeBuffer([{ id: "server", title: "Server", body: "body" }])).not.toThrow()
      expect(readBuffer()).toEqual([])
    } finally {
      vi.stubGlobal("window", browserWindow)
    }
  })

  it("does not touch browser storage when the window global is absent", () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window")
    expect(descriptor).toBeDefined()
    const deleted = Reflect.deleteProperty(globalThis, "window")
    expect(deleted).toBe(true)
    try {
      expect(getToastStorage()).toBeNull()
      expect(readBuffer()).toEqual([])
      expect(() =>
        writeBuffer([{ id: "server-no-window", title: "Server", body: "body" }])
      ).not.toThrow()
    } finally {
      if (descriptor) Object.defineProperty(globalThis, "window", descriptor)
    }
  })

  it("fails closed when browser storage access itself is denied", () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage")
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get: () => {
        throw new Error("storage access denied")
      },
    })
    try {
      expect(getToastStorage()).toBeNull()
      expect(readBuffer()).toEqual([])
      expect(() =>
        writeBuffer([{ id: "blocked", title: "Blocked", body: "Storage denied" }])
      ).not.toThrow()
    } finally {
      if (descriptor) Object.defineProperty(window, "localStorage", descriptor)
      else delete (window as unknown as { localStorage?: Storage }).localStorage
    }
  })

  it("returns null when browser storage is unavailable", () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage")
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: undefined,
    })

    try {
      expect(getToastStorage()).toBeNull()
      render(<LivePushToasts />)
    } finally {
      if (descriptor) Object.defineProperty(window, "localStorage", descriptor)
      else delete (window as unknown as { localStorage?: Storage }).localStorage
    }
  })

  it("fails closed when storage methods are not callable", () => {
    const storage = window.localStorage
    const getDescriptor = Object.getOwnPropertyDescriptor(storage, "getItem")
    const setDescriptor = Object.getOwnPropertyDescriptor(storage, "setItem")
    const removeDescriptor = Object.getOwnPropertyDescriptor(storage, "removeItem")
    Object.defineProperty(storage, "getItem", { configurable: true, value: null })
    Object.defineProperty(storage, "setItem", { configurable: true, value: null })
    Object.defineProperty(storage, "removeItem", { configurable: true, value: null })
    try {
      expect(readBuffer()).toEqual([])
      expect(() =>
        writeBuffer([{ id: "non-callable", title: "Safe", body: "Storage" }])
      ).not.toThrow()
      expect(() => render(<LivePushToasts />)).not.toThrow()
    } finally {
      if (getDescriptor) Object.defineProperty(storage, "getItem", getDescriptor)
      else Reflect.deleteProperty(storage, "getItem")
      if (setDescriptor) Object.defineProperty(storage, "setItem", setDescriptor)
      else Reflect.deleteProperty(storage, "setItem")
      if (removeDescriptor) Object.defineProperty(storage, "removeItem", removeDescriptor)
      else Reflect.deleteProperty(storage, "removeItem")
    }
  })

  it("leaves the legacy buffer untouched when storage removal is unavailable", () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage")
    const backingStorage = window.localStorage
    backingStorage.setItem("livePushToastBuffer", "legacy-buffer-retained")
    const storageFacade = {
      clear: backingStorage.clear.bind(backingStorage),
      getItem: backingStorage.getItem.bind(backingStorage),
      key: backingStorage.key.bind(backingStorage),
      get length() {
        return backingStorage.length
      },
      removeItem: null,
      setItem: backingStorage.setItem.bind(backingStorage),
    } as unknown as Storage
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: storageFacade,
    })

    try {
      const storage = getToastStorage()
      expect(storage).toBe(storageFacade)
      expect((storage as unknown as { removeItem: unknown }).removeItem).toBeNull()
      expect(() => render(<LivePushToasts />)).not.toThrow()
      expect(backingStorage.getItem("livePushToastBuffer")).toBe("legacy-buffer-retained")
    } finally {
      if (descriptor) Object.defineProperty(window, "localStorage", descriptor)
      else delete (window as unknown as { localStorage?: Storage }).localStorage
    }
  })

  it("keeps the seen-id window duplicate-free while evicting its oldest entry", () => {
    const seen = new Set<string>()
    expect(rememberToastId(seen, "first")).toBe(true)
    expect(rememberToastId(seen, "first")).toBe(false)
    for (let index = 1; index < 256; index += 1)
      expect(rememberToastId(seen, `id-${index}`)).toBe(true)
    expect(seen.size).toBe(256)
    expect(rememberToastId(seen, "newest")).toBe(true)
    expect(seen.size).toBe(256)
    expect(seen.has("first")).toBe(false)
    expect(rememberToastId(seen, "newest")).toBe(false)
  })

  it("renders nothing initially (no queued toasts)", () => {
    render(<LivePushToasts />)
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("keeps toast entrance motion compositor-safe and bounded", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-motion",
        title: "Motion contract",
        body: "Only opacity and transform should animate",
      },
    })

    const toastMotion = motionCapture.divProps.find((props) => {
      const initial = props.initial
      return (
        typeof initial === "object" && initial !== null && "opacity" in initial && "y" in initial
      )
    })
    expect(toastMotion).toBeDefined()
    expect(toastMotion).toEqual(
      expect.objectContaining({
        initial: { opacity: 0, y: -20 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -10 },
        transition: { duration: 0.2, ease: "easeOut" },
      })
    )
    for (const phase of ["initial", "animate", "exit"] as const) {
      expect(Object.keys(toastMotion?.[phase] as object)).toEqual(
        expect.arrayContaining(["opacity", "y"])
      )
      expect(Object.keys(toastMotion?.[phase] as object)).not.toContain("filter")
    }
    expect((toastMotion?.transition as Record<string, unknown>).type).toBeUndefined()
    const progressMotion = motionCapture.divProps.find((props) => {
      const initial = props.initial
      return typeof initial === "object" && initial !== null && "width" in initial
    })
    expect(progressMotion).toEqual(
      expect.objectContaining({
        className: "absolute bottom-0 left-0 h-0.5 opacity-heavy text-brand",
        initial: { width: "100%" },
        animate: { width: "0%" },
        transition: { duration: 6, ease: "linear" },
        style: { background: "linear-gradient(to right, currentColor, transparent)" },
      })
    )
  })

  it("subscribes to the service-worker message channel on mount", () => {
    render(<LivePushToasts />)
    expect(messageHandler).toBeTypeOf("function")
    expect(translationState.namespaces).toEqual(["notifications", "common"])
  })

  it("renders safely when service-worker messaging is unavailable", () => {
    const serviceWorker = navigator.serviceWorker
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: undefined,
    })

    try {
      render(<LivePushToasts />)
      expect(messageHandler).toBeNull()
      expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
    } finally {
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: serviceWorker,
      })
    }
  })

  it("renders a success toast (CheckCircle icon) from a PUSH_NOTIFICATION message", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-success",
        title: "Saved",
        body: "Your changes were saved",
        data: { severity: "success" },
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Saved")).toBeInTheDocument()
    expect(screen.getByText("Your changes were saved")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-success-border")
    expect(screen.getByRole("status").querySelector("div.shrink-0")).toHaveClass(
      "text-success-text"
    )
  })

  it("renders an info toast for an unknown/missing severity (default branch)", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "t-info", title: "Heads up", body: "Something happened" },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Heads up")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-brand")
  })

  it("normalizes severity casing and surrounding whitespace", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "normalized-severity",
        title: "Normalized warning",
        body: "Severity is case-insensitive",
        data: { severity: "  WARNING  " },
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByRole("status")).toHaveClass("border-l-warning-border")
  })

  it("falls back to a finite timestamp when id metadata has the wrong type", async () => {
    render(<LivePushToasts />)

    const message = {
      type: "PUSH_NOTIFICATION",
      toast: {
        id: 123,
        tag: { unexpected: true },
        timestamp: 0,
        title: "Timestamp identity",
        body: "Zero is still a valid finite timestamp",
      },
    }
    await dispatchSwMessage(message)
    await dispatchSwMessage(message)
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getAllByText("Timestamp identity")).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByText("Timestamp identity")).not.toBeInTheDocument()
  })

  it("trims identity metadata and gives an explicit id precedence over tag/timestamp", async () => {
    render(<LivePushToasts />)

    const canonical = {
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "  canonical-id  ",
        tag: "different-tag",
        timestamp: 1700000000000,
        title: "Canonical identity",
        body: "The trimmed id is the deduplication key",
      },
    }
    await dispatchSwMessage(canonical)
    await dispatchSwMessage({
      ...canonical,
      toast: { ...canonical.toast, id: "canonical-id", title: "Canonical identity replay" },
    })
    act(() => vi.advanceTimersByTime(0))

    expect(screen.getByText("Canonical identity")).toBeInTheDocument()
    expect(screen.queryByText("Canonical identity replay")).not.toBeInTheDocument()
  })

  it("uses a trimmed tag before a finite timestamp when the id is absent", async () => {
    render(<LivePushToasts />)

    const tagged = {
      type: "PUSH_NOTIFICATION",
      toast: {
        tag: "  stable-tag  ",
        timestamp: 1700000000001,
        title: "Tagged identity",
        body: "Tag is preferred",
      },
    }
    await dispatchSwMessage(tagged)
    await dispatchSwMessage({
      ...tagged,
      toast: { ...tagged.toast, tag: "stable-tag", title: "Tagged identity replay" },
    })
    act(() => vi.advanceTimersByTime(0))

    expect(screen.getByText("Tagged identity")).toBeInTheDocument()
    expect(screen.queryByText("Tagged identity replay")).not.toBeInTheDocument()
  })

  it("generates independent fallback identities for payloads without usable metadata", async () => {
    const randomSpy = vi.spyOn(Math, "random").mockReturnValueOnce(0.111).mockReturnValueOnce(0.222)
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1700000000000)
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "", tag: " ", timestamp: Number.NaN, title: "Generated one", body: "First" },
    })
    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "",
        tag: " ",
        timestamp: Number.POSITIVE_INFINITY,
        title: "Generated two",
        body: "Second",
      },
    })
    act(() => vi.advanceTimersByTime(0))

    expect(screen.getByText("Generated one")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => vi.advanceTimersByTime(300))
    expect(screen.getByText("Generated two")).toBeInTheDocument()

    randomSpy.mockRestore()
    nowSpy.mockRestore()
  })

  it("deduplicates repeated visible notifications by their canonical id", async () => {
    render(<LivePushToasts />)

    const message = {
      type: "PUSH_NOTIFICATION",
      toast: { id: "duplicate-visible", title: "Only once", body: "Do not replay" },
    }
    await dispatchSwMessage(message)
    await dispatchSwMessage(message)
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getAllByText("Only once")).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByText("Only once")).not.toBeInTheDocument()
  })

  it("falls back for non-string and unknown severity values", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-invalid-severity",
        title: "Invalid severity",
        body: "Falls back to info",
        data: { severity: 42 },
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("Invalid severity")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-unknown-severity",
        title: "Unknown severity",
        body: "Also falls back",
        data: { severity: "not-a-severity" },
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("Unknown severity")).toBeInTheDocument()
  })

  it("generates a stable-enough fallback id when push metadata has no id", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { title: "Generated id", body: "No id, tag, or timestamp" },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("Generated id")).toBeInTheDocument()
  })

  it("renders a warning toast", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-warn",
        title: "Careful",
        body: "Low disk space",
        data: { severity: "warning" },
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Careful")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-warning-border")
    expect(screen.getByRole("status").querySelector("div.shrink-0")).toHaveClass(
      "text-warning-text"
    )
  })

  it("renders an error toast", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-error",
        title: "Failed",
        body: "Upload failed",
        data: { severity: "error" },
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Failed")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-error-border")
    expect(screen.getByRole("status").querySelector("div.shrink-0")).toHaveClass("text-error-text")
  })

  it("announces visible toasts and keeps action targets touch accessible", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "a11y-toast",
        title: "Accessible notification",
        body: "Assistive technology should announce this",
        url: "/events/1",
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    const toast = screen.getByRole("status")
    expect(toast).toHaveAttribute("aria-live", "polite")
    expect(toast).toHaveAttribute("aria-atomic", "true")
    expect(toast).toHaveClass(
      "pointer-events-auto",
      "relative",
      "overflow-hidden",
      "flex",
      "items-start",
      "gap-4",
      "p-4",
      "rounded-2xl",
      "glass-noise",
      "backdrop-blur-2xl",
      "border",
      "border-(--glass-border)",
      "shadow-premium",
      "bg-(--glass-bg-high)",
      "dark:bg-(--glass-bg-high)",
      "border-l-[3px]",
      "border-l-brand"
    )
    expect(toast.querySelector("div.shrink-0")).toHaveClass(
      "shrink-0",
      "mt-0.5",
      "relative",
      "z-base",
      "text-brand"
    )
    expect(screen.getByRole("button", { name: "common:buttons.close" })).toHaveClass(
      "min-h-11",
      "min-w-11"
    )
    expect(screen.getByRole("button", { name: "common:buttons.close" })).toHaveClass(
      "group/btn",
      "relative",
      "z-base",
      "flex",
      "h-7",
      "w-7",
      "min-h-11",
      "min-w-11",
      "items-center",
      "justify-center",
      "rounded-full",
      "bg-linear-to-tr",
      "from-white/[calc(var(--opacity-faint)*100%)]",
      "to-white/[calc(var(--opacity-subtle)*100%)]",
      "text-(--text-secondary)",
      "transition-all",
      "duration-base",
      "hover:scale-110",
      "hover:shadow-premium",
      "active:scale-95"
    )
    expect(screen.getByRole("button", { name: "notifications:toast.open" })).toHaveClass("min-h-11")
  })

  it("ignores a PUSH_NOTIFICATION with no content (empty title and body)", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "blank", title: "", body: "" },
    })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("ignores a PUSH_NOTIFICATION message without a toast payload", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "PUSH_NOTIFICATION" })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("ignores push payloads with malformed field types without throwing", async () => {
    render(<LivePushToasts />)

    await expect(
      dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: {
          id: 123,
          tag: { unexpected: true },
          title: 456,
          body: { unexpected: true },
          url: { unexpected: true },
        },
      })
    ).resolves.toBeUndefined()

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("trims content before rendering and rejects whitespace-only content", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "trimmed-content", title: "  Trimmed title  ", body: "  Trimmed body  " },
    })
    act(() => vi.advanceTimersByTime(0))

    expect(screen.getByText("Trimmed title")).toBeInTheDocument()
    expect(screen.getByText("Trimmed body")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => vi.advanceTimersByTime(300))

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "whitespace-content", title: "   ", body: "\t\n" },
    })
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("ignores non-object toast payloads without rendering or throwing", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "PUSH_NOTIFICATION", toast: "not-an-object" })
    await dispatchSwMessage({ type: "PUSH_NOTIFICATION", toast: [] })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("uses localized defaults for omitted title or body", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "missing-title", body: "Body without a title" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("notifications:defaultTitle")).toBeInTheDocument()
    expect(screen.getByText("Body without a title")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "missing-body", title: "Title without a body" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("Title without a body")).toBeInTheDocument()
    expect(screen.getByText("notifications:defaultBody")).toBeInTheDocument()
  })

  it("renders a sync-complete toast from a SYNC_COMPLETE message (i18n keys)", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "SYNC_COMPLETE" })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("notifications:sync.title")).toBeInTheDocument()
    expect(screen.getByText("notifications:sync.body")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-success-border")
  })

  it("refreshes the message subscription when the translator changes", async () => {
    const view = render(<LivePushToasts />)
    translationState.emptySync = true
    view.rerender(<LivePushToasts />)

    await dispatchSwMessage({ type: "SYNC_COMPLETE" })
    act(() => vi.advanceTimersByTime(0))
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("keeps visibility handling stable across renders while flushing newly visible storage", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    const addListenerSpy = vi.spyOn(document, "addEventListener")
    try {
      const view = render(<LivePushToasts />)
      const initialVisibilitySubscriptions = addListenerSpy.mock.calls.filter(
        ([type]) => type === "visibilitychange"
      ).length
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "rerender-buffer", title: "Rerender buffer", body: "Flush once visible" },
      })
      expect(screen.queryByText("Rerender buffer")).not.toBeInTheDocument()

      visibilitySpy.mockReturnValue("visible")
      view.rerender(<LivePushToasts />)
      expect(addListenerSpy.mock.calls.filter(([type]) => type === "visibilitychange").length).toBe(
        initialVisibilitySubscriptions
      )
      act(() => document.dispatchEvent(new Event("visibilitychange")))
      act(() => vi.advanceTimersByTime(0))
      expect(screen.getByText("Rerender buffer")).toBeInTheDocument()
    } finally {
      addListenerSpy.mockRestore()
      visibilitySpy.mockRestore()
    }
  })

  it("ignores an empty localized sync-complete toast", async () => {
    translationState.emptySync = true
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "SYNC_COMPLETE" })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("dismisses the current toast when the close button is clicked", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "t-close", title: "Closable", body: "Tap to close" },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Closable")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(300)
    })

    expect(screen.queryByText("Closable")).not.toBeInTheDocument()
  })

  it("does not let repeated close actions clear the next queued toast", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "first-close", title: "First toast", body: "Dismiss me" },
    })
    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "second-close", title: "Second toast", body: "Keep me visible" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    fireEvent.click(closeButton)
    // A rapid second click can target the exiting DOM node before the animation completes.
    fireEvent.click(closeButton)

    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.getByText("Second toast")).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.getByText("Second toast")).toBeInTheDocument()
  })

  it("replaces an active close timer when close is invoked twice in one interaction", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "double-close", title: "Double close", body: "Reset the timer" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    act(() => {
      // Keep both events in the same React batch so the second event reaches
      // the still-mounted control before the exit state commits.
      closeButton.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      closeButton.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    expect(vi.getTimerCount()).toBe(1)
  })

  it("evicts the oldest seen id after the deduplication window is full", () => {
    render(<LivePushToasts />)

    act(() => {
      for (let index = 0; index <= 256; index += 1) {
        messageHandler?.({
          data: {
            type: "PUSH_NOTIFICATION",
            recipientUserId: TEST_USER_A_ID,
            toast: { id: `seen-${index}`, title: `Toast ${index}`, body: "Seen window" },
          },
        } as MessageEvent)
      }
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Toast 0")).toBeInTheDocument()
  })

  it("cleans up the deferred close timer when the toast unmounts", async () => {
    const view = render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "unmount-close", title: "Unmount me", body: "No timer leak" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(vi.getTimerCount()).toBe(1)

    view.rerender(<LivePushToasts />)
    expect(vi.getTimerCount()).toBe(1)

    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("renders an action button when the toast carries a safe URL, and opening it dismisses the toast", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-url",
        title: "Open me",
        body: "Has a link",
        url: "https://example.com/path",
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    const actionButton = screen.getByText("notifications:toast.open")
    expect(actionButton).toBeInTheDocument()

    fireEvent.click(actionButton)

    expect(openSpy).toHaveBeenCalledWith(
      "https://example.com/path",
      "_blank",
      "noopener,noreferrer"
    )

    act(() => {
      vi.advanceTimersByTime(300)
    })

    expect(screen.queryByText("Open me")).not.toBeInTheDocument()

    openSpy.mockRestore()
  })

  it("falls back to a new-tab open when the initial action open throws", async () => {
    const openSpy = vi
      .spyOn(window, "open")
      .mockImplementationOnce(() => {
        throw new Error("popup blocked")
      })
      .mockReturnValue(null)
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-url-fallback",
        title: "Fallback open",
        body: "Browser blocks the first attempt",
        url: "https://example.com/path",
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })
    fireEvent.click(screen.getByText("notifications:toast.open"))

    expect(openSpy).toHaveBeenCalledTimes(2)
    expect(openSpy).toHaveBeenLastCalledWith(
      "https://example.com/path",
      "_blank",
      "noopener,noreferrer"
    )
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByText("Fallback open")).not.toBeInTheDocument()
    openSpy.mockRestore()
  })

  it("opens a same-origin action in the current tab", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-same-origin",
        title: "Open internally",
        body: "Same-origin action",
        url: "/events/42",
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    fireEvent.click(screen.getByText("notifications:toast.open"))

    expect(openSpy).toHaveBeenCalledWith(`${window.location.origin}/events/42`, "_self", undefined)
    openSpy.mockRestore()
  })

  it("ignores a stale action click after the toast has been closed", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-stale-action",
        title: "Stale action",
        body: "Close before the delayed click",
        url: "/events/stale",
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    const actionButton = screen.getByText("notifications:toast.open")
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })

    expect(() => fireEvent.click(actionButton)).not.toThrow()
    expect(openSpy).not.toHaveBeenCalled()
    openSpy.mockRestore()
  })

  it("strips an unsafe (non-http) URL so no action button is shown", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-bad-url",
        title: "No link",
        body: "Unsafe scheme",
        url: "javascript:alert(1)",
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("No link")).toBeInTheDocument()
    expect(screen.queryByText("notifications:toast.open")).not.toBeInTheDocument()
  })

  it("auto-dismisses the toast after TOAST_LONG via the timeout", async () => {
    render(<LivePushToasts />)

    act(() => {
      messageHandler?.({
        data: {
          type: "PUSH_NOTIFICATION",
          recipientUserId: TEST_USER_A_ID,
          toast: { id: "t-auto", title: "Auto", body: "Goes away" },
        },
      } as MessageEvent)
    })
    // flush the enqueue microtask + the queue→current effect
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Auto")).toBeInTheDocument()

    // TOAST_LONG (6000) + the 300ms handleClose unmount delay.
    act(() => {
      vi.advanceTimersByTime(6000 + 300)
    })

    expect(screen.queryByText("Auto")).not.toBeInTheDocument()
  })

  it("flushes buffered toasts from localStorage on a visibility change to visible", async () => {
    // Seed a buffered toast directly into storage (as if it arrived while hidden).
    window.localStorage.setItem(
      BUFFER_STORAGE_KEY,
      JSON.stringify([{ id: "buffered-1", title: "Buffered", body: "From storage" }])
    )

    render(<LivePushToasts />)

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Buffered")).toBeInTheDocument()
    // Buffer is consumed (cleared) after flushing.
    expect(window.localStorage.getItem(BUFFER_STORAGE_KEY)).toBe("[]")
  })

  it("deduplicates a buffered notification against one delivered before the visibility flush", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")

    try {
      render(<LivePushToasts />)

      const duplicate = {
        type: "PUSH_NOTIFICATION",
        toast: { id: "flush-race", title: "Flush race", body: "Only one delivery" },
      }
      await dispatchSwMessage(duplicate)
      expect(screen.queryByText("Flush race")).not.toBeInTheDocument()

      visibilitySpy.mockReturnValue("visible")
      await dispatchSwMessage(duplicate)
      act(() => {
        vi.advanceTimersByTime(0)
      })
      expect(screen.getByText("Flush race")).toBeInTheDocument()

      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"))
      })

      fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
      act(() => {
        vi.advanceTimersByTime(300)
      })

      expect(screen.queryByText("Flush race")).not.toBeInTheDocument()
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("marks restored notifications as seen so later live delivery is not replayed", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")

    try {
      render(<LivePushToasts />)

      const buffered = {
        type: "PUSH_NOTIFICATION",
        toast: { id: "restored-seen", title: "Restored once", body: "Do not replay" },
      }
      await dispatchSwMessage(buffered)

      visibilitySpy.mockReturnValue("visible")
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"))
      })
      expect(screen.getByText("Restored once")).toBeInTheDocument()

      await dispatchSwMessage(buffered)
      act(() => {
        vi.advanceTimersByTime(0)
      })

      fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
      act(() => {
        vi.advanceTimersByTime(300)
      })

      expect(screen.queryByText("Restored once")).not.toBeInTheDocument()
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("restores tag/timestamp ids and filters malformed buffered entries", () => {
    window.localStorage.setItem(
      BUFFER_STORAGE_KEY,
      JSON.stringify([
        null,
        42,
        {},
        { tag: "buffer-tag", title: "Tagged", body: "Tag id" },
        { timestamp: 1700000000000, title: "Timestamped", body: "Timestamp id" },
      ])
    )

    render(<LivePushToasts />)
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Tagged")).toBeInTheDocument()
    expect(screen.queryByText("Timestamped")).not.toBeInTheDocument()
    expect(window.localStorage.getItem(BUFFER_STORAGE_KEY)).toBe("[]")
  })

  it("ignores a non-array persisted buffer", () => {
    window.localStorage.setItem(BUFFER_STORAGE_KEY, JSON.stringify({ unexpected: true }))

    render(<LivePushToasts />)

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("ignores a storage read failure while flushing the buffer", () => {
    const getItemSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })

    render(<LivePushToasts />)

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
    getItemSpy.mockRestore()
  })

  it("buffers a PUSH_NOTIFICATION when the document is hidden instead of showing it", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "hidden-1", title: "Hidden push", body: "Should buffer" },
    })

    // Not rendered while hidden …
    expect(screen.queryByText("Hidden push")).not.toBeInTheDocument()
    // … but written to the buffer for later flush.
    const raw = window.localStorage.getItem(BUFFER_STORAGE_KEY)
    expect(raw).toContain("hidden-1")

    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"))
    })
    expect(screen.queryByText("Hidden push")).not.toBeInTheDocument()

    visibilitySpy.mockRestore()
  })

  it("does not buffer hidden pushes in the test transport sentinel mode", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    const previousName = window.name
    window.name = "__mock_api_initialized__"
    try {
      render(<LivePushToasts />)
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "sentinel-hidden", title: "Sentinel push", body: "Render for tests" },
      })
      act(() => vi.advanceTimersByTime(0))
      expect(screen.getByText("Sentinel push")).toBeInTheDocument()
      expect(window.localStorage.getItem(BUFFER_STORAGE_KEY)).toBeNull()
    } finally {
      window.name = previousName
      visibilitySpy.mockRestore()
    }
  })

  it("bounds the persisted hidden buffer to the newest twenty notifications", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    try {
      render(<LivePushToasts />)
      for (let index = 0; index < 25; index += 1) {
        await dispatchSwMessage({
          type: "PUSH_NOTIFICATION",
          toast: { id: `buffer-bound-${index}`, title: `Buffered ${index}`, body: "Bounded" },
        })
      }
      const persisted = JSON.parse(
        window.localStorage.getItem(BUFFER_STORAGE_KEY) ?? "null"
      ) as Array<{
        id: string
      }>
      expect(persisted).toHaveLength(20)
      expect(persisted[0]?.id).toBe("buffer-bound-5")
      expect(persisted.at(-1)?.id).toBe("buffer-bound-24")
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("ignores a storage write failure while buffering a hidden push", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "hidden-write-failure", title: "Hidden push", body: "Should be ignored" },
    })

    expect(screen.queryByText("Hidden push")).not.toBeInTheDocument()
    setItemSpy.mockRestore()
    visibilitySpy.mockRestore()
  })

  it("ignores unrelated service-worker message types", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "SOME_OTHER_TYPE" })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("keeps a new account buffer when its push arrives before prior identity cleanup", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")

    try {
      render(<LivePushToasts />)
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "prior-hidden", title: "Prior account", body: "Private prior" },
      })
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toContain("prior-hidden")

      act(() => {
        useAuthStore.setState({
          user: {
            id: TEST_USER_B_ID,
            email: "toast-user-b@example.test",
            is_active: true,
          },
          loading: false,
        })
        messageHandler?.({
          data: {
            type: "PUSH_NOTIFICATION",
            recipientUserId: TEST_USER_B_ID,
            toast: {
              id: "next-hidden",
              title: "Next account",
              body: "Private next",
            },
          },
        } as MessageEvent)
      })

      expect(JSON.parse(window.localStorage.getItem(TEST_USER_B_BUFFER_KEY) ?? "[]")).toMatchObject(
        [{ id: "next-hidden", title: "Next account", body: "Private next" }]
      )
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toBeNull()
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("flushes an account buffer after anonymous-to-authenticated transition", () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
    useAuthStore.setState({ user: null, loading: false })

    try {
      render(<LivePushToasts />)
      window.localStorage.setItem(
        TEST_USER_A_BUFFER_KEY,
        JSON.stringify([
          { id: "login-buffer", title: "Login buffer", body: "Current account only" },
        ])
      )

      act(() => {
        useAuthStore.setState({
          user: {
            id: TEST_USER_A_ID,
            email: "toast-user-a@example.test",
            is_active: true,
          },
          loading: false,
        })
      })
      act(() => vi.advanceTimersByTime(0))

      expect(screen.getByText("Login buffer")).toBeInTheDocument()
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toBe("[]")
    } finally {
      visibilitySpy.mockRestore()
    }
  })
  it("keeps persisted hidden pushes bound to the confirmed account during an account switch", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")

    try {
      render(<LivePushToasts />)
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "account-a-hidden", title: "Account A", body: "Private A" },
      })
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toContain("account-a-hidden")

      visibilitySpy.mockReturnValue("visible")
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"))
      })
      act(() => vi.advanceTimersByTime(0))
      expect(screen.getByText("Account A")).toBeInTheDocument()

      visibilitySpy.mockReturnValue("hidden")
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "account-a-buffered", title: "Account A buffered", body: "Private A" },
      })
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toContain("account-a-buffered")

      const unmountsBeforeAccountSwitch = motionCapture.presenceUnmounts
      act(() =>
        useAuthStore.setState({ user: { id: TEST_USER_B_ID } as UserState, loading: false })
      )
      expect(motionCapture.presenceUnmounts).toBe(unmountsBeforeAccountSwitch + 1)
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toBeNull()
      expect(screen.queryByText("Account A")).not.toBeInTheDocument()
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "account-b-hidden", title: "Account B", body: "Private B" },
      })
      expect(window.localStorage.getItem(TEST_USER_B_BUFFER_KEY)).toContain("account-b-hidden")

      visibilitySpy.mockReturnValue("visible")
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"))
      })
      act(() => vi.advanceTimersByTime(0))

      expect(screen.getByText("Account B")).toBeInTheDocument()
      expect(screen.queryByText("Account A")).not.toBeInTheDocument()
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("does not persist anonymous pushes or restore the legacy shared buffer", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    useAuthStore.setState({ user: null, loading: false })
    window.localStorage.setItem(
      "livePushToastBuffer",
      JSON.stringify([
        { id: "legacy-shared", title: "Legacy account toast", body: "Must be discarded" },
      ])
    )

    try {
      render(<LivePushToasts />)
      expect(window.localStorage.getItem("livePushToastBuffer")).toBeNull()
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "anonymous-hidden", title: "Anonymous toast", body: "Do not persist" },
      })
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toBeNull()
      expect(window.localStorage.getItem(TEST_USER_B_BUFFER_KEY)).toBeNull()

      visibilitySpy.mockReturnValue("visible")
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"))
      })
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "anonymous-visible", title: "Anonymous live toast", body: "Do not display" },
      })
      act(() => vi.advanceTimersByTime(0))
      expect(screen.queryByText("Legacy account toast")).not.toBeInTheDocument()
      expect(screen.queryByText("Anonymous toast")).not.toBeInTheDocument()
      expect(screen.queryByText("Anonymous live toast")).not.toBeInTheDocument()
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("clears the account buffer and active toast on logout", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")

    try {
      render(<LivePushToasts />)
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "logout-buffered", title: "Logout buffer", body: "Private A" },
      })
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toContain("logout-buffered")

      visibilitySpy.mockReturnValue("visible")
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"))
      })
      act(() => vi.advanceTimersByTime(0))
      expect(screen.getByText("Logout buffer")).toBeInTheDocument()

      visibilitySpy.mockReturnValue("hidden")
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "logout-queued", title: "Logout queued", body: "Private queue" },
      })
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toContain("logout-queued")

      act(() => useAuthStore.setState({ user: null, loading: false }))
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toBeNull()
      expect(screen.queryByText("Logout buffer")).not.toBeInTheDocument()

      visibilitySpy.mockReturnValue("visible")
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"))
      })
      act(() => vi.advanceTimersByTime(0))
      expect(screen.queryByText("Logout queued")).not.toBeInTheDocument()
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("restores a confirmed account buffer after a component reload", () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")

    try {
      window.localStorage.setItem(
        TEST_USER_A_BUFFER_KEY,
        JSON.stringify([
          { id: "reload-buffered", title: "Reloaded account toast", body: "Same account" },
        ])
      )

      render(<LivePushToasts />)
      act(() => vi.advanceTimersByTime(0))

      expect(screen.getByText("Reloaded account toast")).toBeInTheDocument()
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toBe("[]")
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("retains the confirmed account toast and buffer during a same-user auth refresh", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")

    try {
      render(<LivePushToasts />)
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "refresh-active", title: "Refresh active", body: "Still visible" },
      })
      act(() => vi.advanceTimersByTime(0))
      expect(screen.getByText("Refresh active")).toBeInTheDocument()

      visibilitySpy.mockReturnValue("hidden")
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "refresh-buffered", title: "Refresh buffered", body: "Keep this" },
      })
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toContain("refresh-buffered")

      act(() => {
        useAuthStore.setState({ user: { id: TEST_USER_A_ID } as UserState, loading: true })
      })

      expect(screen.getByText("Refresh active")).toBeInTheDocument()
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toContain("refresh-buffered")
    } finally {
      visibilitySpy.mockRestore()
    }
  })

  it("hides the prior account toast while a different identity is still unconfirmed", async () => {
    render(<LivePushToasts />)
    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "unconfirmed-switch-a", title: "Private A", body: "Must disappear" },
    })
    act(() => vi.advanceTimersByTime(0))
    expect(screen.getByText("Private A")).toBeInTheDocument()

    act(() => {
      useAuthStore.setState({ user: { id: TEST_USER_B_ID } as UserState, loading: true })
    })
    expect(screen.queryByText("Private A")).not.toBeInTheDocument()

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "unconfirmed-switch-b", title: "Unconfirmed B", body: "Must wait" },
    })
    expect(screen.queryByText("Unconfirmed B")).not.toBeInTheDocument()
  })

  it("clears stale active toasts across a batched logout and same-account login", async () => {
    render(<LivePushToasts />)
    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "logout-login-stale", title: "Old session toast", body: "Must stay cleared" },
    })
    act(() => vi.advanceTimersByTime(0))
    expect(screen.getByText("Old session toast")).toBeInTheDocument()

    act(() => {
      useAuthStore.setState({ user: null, loading: false })
      useAuthStore.setState({ user: { id: TEST_USER_A_ID } as UserState, loading: false })
    })

    expect(screen.queryByText("Old session toast")).not.toBeInTheDocument()
  })

  it("invalidates active and queued notifications after a cross-tab session rotation", async () => {
    const previousGeneration = window.localStorage.getItem(SESSION_GENERATION_KEY)
    const ownerGeneration = JSON.stringify({ nonce: "push-session-owner", hash: null })
    window.localStorage.setItem(SESSION_GENERATION_KEY, ownerGeneration)
    acceptBrowserSessionGeneration()

    try {
      render(<LivePushToasts />)
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "cross-tab-active", title: "Prior session active", body: "Must hide" },
      })
      await dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: { id: "cross-tab-queued", title: "Prior session queued", body: "Must drop" },
      })
      act(() => vi.advanceTimersByTime(0))
      expect(screen.getByText("Prior session active")).toBeInTheDocument()

      window.localStorage.setItem(
        TEST_USER_A_BUFFER_KEY,
        JSON.stringify([
          { id: "cross-tab-persisted", title: "Prior session stored", body: "Must clear" },
        ])
      )
      const nextGeneration = JSON.stringify({ nonce: "push-session-next", hash: null })
      window.localStorage.setItem(SESSION_GENERATION_KEY, nextGeneration)
      await act(async () => {
        window.dispatchEvent(
          new StorageEvent("storage", {
            key: SESSION_GENERATION_KEY,
            newValue: nextGeneration,
          })
        )
      })

      expect(screen.queryByText("Prior session active")).not.toBeInTheDocument()
      expect(screen.queryByText("Prior session queued")).not.toBeInTheDocument()
      expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toBeNull()

      act(() => vi.advanceTimersByTime(7000))
      expect(screen.queryByText("Prior session queued")).not.toBeInTheDocument()
    } finally {
      if (previousGeneration === null) {
        window.localStorage.removeItem(SESSION_GENERATION_KEY)
      } else {
        window.localStorage.setItem(SESSION_GENERATION_KEY, previousGeneration)
      }
      acceptBrowserSessionGeneration()
    }
  })

  it("uses the anonymous server identity snapshot during SSR", () => {
    expect(renderToString(<LivePushToasts />)).not.toContain('role="status"')
  })

  it("does not read, write, or buffer a toast without a confirmed account", () => {
    useAuthStore.setState({ user: null, loading: false })
    const anonymousToast: ActiveToast = {
      id: "anonymous-helper",
      title: "Anonymous",
      body: "No owner",
    }

    expect(readBuffer()).toEqual([])
    writeBuffer([anonymousToast])
    bufferToast(anonymousToast)

    expect(window.localStorage.getItem(TEST_USER_A_BUFFER_KEY)).toBeNull()
    expect(window.localStorage.getItem(TEST_USER_B_BUFFER_KEY)).toBeNull()
  })

  it("drops queued notifications before React commits an account transition", async () => {
    render(<LivePushToasts />)
    act(() => {
      messageHandler?.({
        data: {
          type: "PUSH_NOTIFICATION",
          recipientUserId: TEST_USER_A_ID,
          toast: { id: "transition-active", title: "A active", body: "Current account" },
        },
      } as MessageEvent)
      messageHandler?.({
        data: {
          type: "PUSH_NOTIFICATION",
          recipientUserId: TEST_USER_A_ID,
          toast: { id: "transition-stale-queued", title: "A queued", body: "Stale account" },
        },
      } as MessageEvent)
      useAuthStore.setState({ user: { id: TEST_USER_B_ID } as UserState, loading: false })
    })
    act(() => vi.advanceTimersByTime(0))

    expect(screen.queryByText("A active")).not.toBeInTheDocument()
    expect(screen.queryByText("A queued")).not.toBeInTheDocument()
  })

  it("rejects a message when an earlier bus subscriber switches accounts", async () => {
    const { subscribeToPushMessages } = await import("@/push/pushMessageBus")
    const changeAccount = subscribeToPushMessages((_event, ownerId) => {
      if (ownerId === TEST_USER_A_ID) {
        useAuthStore.setState({ user: { id: TEST_USER_B_ID } as UserState, loading: false })
      }
    })
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "reentrant-stale", title: "Stale delivery", body: "Account changed" },
    })

    expect(screen.queryByText("Stale delivery")).not.toBeInTheDocument()
    changeAccount()
  })
})
