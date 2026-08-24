/** @vitest-environment node */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderToString } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: vi.fn(),
  myEventsApiV1EventsMyGet: vi.fn(),
}))

import { useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"

function SsrProbe() {
  const events = useEventsListQuery({ language: "en" }, { enabled: false })
  const mine = useMyEventsQuery({ language: "en", userId: null })
  return <span>{`${events.data === undefined}:${mine.data === undefined}`}</span>
}

describe("events hooks SSR fallbacks", () => {
  it("does not read browser storage while rendering on the server", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    expect(
      renderToString(
        <QueryClientProvider client={queryClient}>
          <SsrProbe />
        </QueryClientProvider>
      )
    ).toContain("<span>true:true</span>")
  })
})
