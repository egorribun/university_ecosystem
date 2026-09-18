// @vitest-environment node

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderToString } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"

import { useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"
import { useNewsListQuery } from "@/api/hooks/news"
import { StorageItem } from "@/utils/storage"

afterEach(() => {
  vi.restoreAllMocks()
})

const OfflineFallbackProbe = () => {
  const news = useNewsListQuery({ language: "en" })
  const events = useEventsListQuery({ language: "en" })
  const myEvents = useMyEventsQuery({ language: "en", userId: null })

  return <span>{`${news.news.length}:${events.events.length}:${String(myEvents.data)}`}</span>
}

describe("offline query fallbacks during SSR", () => {
  it("renders without touching browser-only storage", () => {
    const storageGet = vi.spyOn(StorageItem.prototype, "get")
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    try {
      expect(
        renderToString(
          <QueryClientProvider client={queryClient}>
            <OfflineFallbackProbe />
          </QueryClientProvider>
        )
      ).toContain("0:0:undefined")
      expect(storageGet).not.toHaveBeenCalled()
    } finally {
      storageGet.mockRestore()
    }
  })
})
