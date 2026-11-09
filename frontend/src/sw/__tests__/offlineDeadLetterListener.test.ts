import { beforeEach, describe, expect, it, vi } from "vitest"

import { reportOfflineDeadLetter } from "@/app/webVitals"
import { OFFLINE_DEAD_LETTER_MESSAGE_TYPE } from "@/constants/serviceWorkerMessages"
import { installOfflineDeadLetterListener } from "../offlineDeadLetterListener"

vi.mock("@/app/webVitals", () => ({ reportOfflineDeadLetter: vi.fn() }))

function createContainer() {
  const controller = {} as ServiceWorker
  const target = new EventTarget()
  const container = Object.assign(target, { controller }) as ServiceWorkerContainer
  const send = (data: unknown, source: ServiceWorker | null = controller) => {
    const event = new MessageEvent("message", { data })
    Object.defineProperty(event, "source", { value: source })
    target.dispatchEvent(event)
  }
  return { container, controller, send }
}

const valid = {
  type: OFFLINE_DEAD_LETTER_MESSAGE_TYPE,
  store: "pending-mutations",
  reason: "retries-exhausted:network",
}

beforeEach(() => vi.clearAllMocks())

describe("offline dead-letter listener trust boundary", () => {
  it.each([
    null,
    undefined,
    false,
    "dead-letter",
    { ...valid, type: "unrelated" },
    { ...valid, store: 1 },
    { ...valid, store: "users" },
    { ...valid, store: "pending-" + "a".repeat(41) },
    { ...valid, reason: null },
    { ...valid, reason: "private@example.test" },
    { ...valid, reason: "a".repeat(65) },
  ])("rejects invalid payload %j from the controlling worker", (payload) => {
    const { container, send } = createContainer()
    installOfflineDeadLetterListener(container)
    send(payload)
    expect(reportOfflineDeadLetter).not.toHaveBeenCalled()
    send(valid)
    expect(reportOfflineDeadLetter).toHaveBeenCalledExactlyOnceWith({
      store: valid.store,
      reason: valid.reason,
    })
  })

  it("rejects noncontrolling senders and follows controller replacement", () => {
    const { container, controller, send } = createContainer()
    installOfflineDeadLetterListener(container)
    installOfflineDeadLetterListener(container)
    send(valid, {} as ServiceWorker)
    send(valid, null)
    Object.defineProperty(container, "controller", { value: null, configurable: true })
    send(valid, controller)
    expect(reportOfflineDeadLetter).not.toHaveBeenCalled()

    const replacement = {} as ServiceWorker
    Object.defineProperty(container, "controller", { value: replacement, configurable: true })
    send(valid, controller)
    expect(reportOfflineDeadLetter).not.toHaveBeenCalled()
    send({ ...valid, privateField: "must not be forwarded" }, replacement)
    expect(reportOfflineDeadLetter).toHaveBeenCalledExactlyOnceWith({
      store: valid.store,
      reason: valid.reason,
    })
  })
})
