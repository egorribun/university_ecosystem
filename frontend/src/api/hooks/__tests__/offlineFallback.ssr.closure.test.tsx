// @vitest-environment node

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderToString } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"
import { useNewsListQuery } from "@/api/hooks/news"

const OfflineFallbackProbe = () => {
  const news = useNewsListQuery({ language: "en" })
  const events = useEventsListQuery({ language: "en" })
  const myEvents = useMyEventsQuery({ language: "en", userId: null })

  return <span>{`${news.news.length}:${events.events.length}:${String(myEvents.data)}`}</span>
}

describe("offline query fallbacks during SSR", () => {
  it("renders without touching browser-only storage", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    expect(
      renderToString(
        <QueryClientProvider client={queryClient}>
          <OfflineFallbackProbe />
        </QueryClientProvider>
      )
    ).toContain("0:0:undefined")
  })
})
