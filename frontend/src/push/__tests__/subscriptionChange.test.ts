import { describe, expect, it, vi } from "vitest"
import { getStrictConsoleDiagnostics, withExpectedConsole } from "@/tests/strictConsole"
import { installPushSubscriptionChangeListener } from "../subscriptionChange"

describe("subscription change notices", () => {
  const setup = () => {
    const worker = {}
    const registration = { active: worker } as unknown as ServiceWorkerRegistration
    const container = {
      controller: null,
      addEventListener: vi.fn(),
    } as unknown as ServiceWorkerContainer
    const sync = vi.fn().mockResolvedValue(null)
    installPushSubscriptionChangeListener(container, registration, sync)
    const calls = vi.mocked(container.addEventListener).mock.calls
    expect(calls).toHaveLength(1)
    expect(calls[0]?.[0]).toBe("message")
    const listener = calls[0]?.[1] as (event: MessageEvent) => void
    return { worker, registration, container, sync, listener }
  }

  it("accepts the active worker before the page is controlled and forwards no message payload", () => {
    const { worker, registration, sync, listener } = setup()
    listener({
      source: worker,
      data: { type: "PUSH_SUBSCRIPTION_CHANGED", endpoint: "private", key: "private" },
    } as unknown as MessageEvent)

    expect(sync).toHaveBeenCalledExactlyOnceWith({ registration, subscriptionChange: true })
  })

  it("ignores other sources and message types, and tracks the active worker after an update", () => {
    const { worker, registration, container, sync, listener } = setup()
    const foreign = {}
    Object.defineProperty(container, "controller", { value: foreign, configurable: true })
    const send = (source: unknown, data: unknown) =>
      listener({ source, data } as unknown as MessageEvent)

    send(foreign, { type: "PUSH_SUBSCRIPTION_CHANGED" })
    send(worker, null)
    send(worker, { type: "OTHER" })
    Object.defineProperty(registration, "active", { value: null, configurable: true })
    send(worker, { type: "PUSH_SUBSCRIPTION_CHANGED" })
    expect(sync).not.toHaveBeenCalled()

    Object.defineProperty(registration, "active", { value: foreign, configurable: true })
    send(worker, { type: "PUSH_SUBSCRIPTION_CHANGED" })
    send(foreign, { type: "PUSH_SUBSCRIPTION_CHANGED" })
    expect(sync).toHaveBeenCalledExactlyOnceWith({ registration, subscriptionChange: true })
  })

  it("does not include an unexpected failure in diagnostics", async () => {
    const { worker, sync, listener } = setup()
    sync.mockRejectedValue(new Error("private endpoint and key"))

    await withExpectedConsole(
      "warn",
      "Failed to sync push subscription after a worker notice",
      async () => {
        listener({
          source: worker,
          data: { type: "PUSH_SUBSCRIPTION_CHANGED" },
        } as unknown as MessageEvent)
        await Promise.resolve()
        await Promise.resolve()
      }
    )
    const warning = getStrictConsoleDiagnostics().find((entry) =>
      entry.args.includes("Failed to sync push subscription after a worker notice")
    )
    expect(warning?.args).toEqual(["Failed to sync push subscription after a worker notice"])
  })
})
