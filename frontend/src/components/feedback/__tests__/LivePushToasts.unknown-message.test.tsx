import { act, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

type PushMessageSubscriber = (event: MessageEvent<unknown>) => void

const busState = vi.hoisted(() => ({
  subscriber: null as PushMessageSubscriber | null,
}))

vi.mock("@/push/pushMessageBus", () => ({
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
      busState.subscriber?.({ data: { type: "UNRELATED" } } as MessageEvent<unknown>)
    })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })
})
