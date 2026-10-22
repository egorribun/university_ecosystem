import { act, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

type PushMessageSubscriber = (event: MessageEvent<unknown>, ownerId: string) => void

const busState = vi.hoisted(() => ({
  subscriber: null as PushMessageSubscriber | null,
  identity: { userId: "unknown-test-user", revision: 1 },
}))

vi.mock("@/push/pushMessageBus", () => ({
  getCurrentPushIdentitySnapshot: () => busState.identity,
  getCurrentPushUserId: () => busState.identity.userId,
  subscribeToPushIdentity: (_subscriber: () => void) => () => {},
  getPushBufferStorageKey: (userId: string) => "livePushToastBuffer:" + encodeURIComponent(userId),
  subscribeToPushMessages: (subscriber: PushMessageSubscriber) => {
    busState.subscriber = subscriber
    return () => {
      if (busState.subscriber === subscriber) busState.subscriber = null
    }
  },
}))

vi.mock("framer-motion", async () => {
  const base = (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
  return { ...base, m: base.m, motion: base.motion }
})

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import LivePushToasts from "@/components/feedback/LivePushToasts"

describe("LivePushToasts unsupported messages", () => {
  beforeEach(() => {
    busState.subscriber = null
  })

  it("ignores a message type outside the canonical push events", () => {
    render(<LivePushToasts />)

    expect(busState.subscriber).toBeTypeOf("function")
    act(() => {
      busState.subscriber?.(
        { data: { type: "UNRELATED" } } as MessageEvent<unknown>,
        "unknown-test-user"
      )
    })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })
})
