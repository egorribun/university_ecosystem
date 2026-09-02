import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { HttpResponse, http } from "msw"
import type { ContextType } from "react"
import { QueryClient } from "@tanstack/react-query"

import Events from "@/pages/Events"
import { AuthContext } from "@/contexts/AuthContext"
import type { Event } from "@/types/Event"
import { server } from "../mocks/server"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const buildEvent = (id: string, title: string, isActive: boolean): Event => {
  const start = new Date(Date.now() + 60 * 60 * 1000)
  const end = new Date(start.getTime() + 60 * 60 * 1000)
  return {
    id,
    title,
    description: `${title} description`,
    title_en: title,
    description_en: `${title} description`,
    location: `Hall ${id}`,
    location_en: `Hall ${id}`,
    event_type: null,
    event_type_en: null,
    starts_at: start.toISOString(),
    ends_at: end.toISOString(),
    created_by: "uuid-1",
    created_at: new Date().toISOString(),
    is_active: isActive,
    speaker: null,
    image_url: null,
    image_url_optimized: null,
    about: null,
    about_en: null,
    files: [],
    participant_count: 0,
    is_registered: null,
    my_qr_token: null,
  }
}

type AuthContextValue = ContextType<typeof AuthContext>

const authValue: AuthContextValue = {
  login: vi.fn(),
  logout: vi.fn(),
  setUser: vi.fn(),
  refresh: vi.fn(),
  submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
  requireMfa: vi.fn().mockResolvedValue(null),
  resetEtagCache: vi.fn(),
  authOperation: false,
}

describe("Events caching", () => {
  it("restores cached data when a 304 response is received after switching tabs", async () => {
    const user = userEvent.setup()
    const activeEvents = [buildEvent("event-1", "Active event 1", true)]
    const archiveEvents = [buildEvent("event-2", "Archived event 1", false)]
    let activeRequestCount = 0

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })

    server.use(
      http.get("*/events", ({ request }) => {
        const url = new URL(request.url)
        const isActive = url.searchParams.get("is_active")
        if (isActive === "true") {
          const ifNoneMatch = request.headers.get("if-none-match")
          if (ifNoneMatch === '"active-tag"') {
            activeRequestCount += 1
            return new HttpResponse(null, {
              status: 304,
              headers: { ETag: '"active-tag"' },
            })
          }
          activeRequestCount += 1
          return HttpResponse.json(
            {
              items: activeEvents,
              total: activeEvents.length,
              limit: 12,
              cursor: null,
              next_cursor: null,
              has_more: false,
            },
            { headers: { ETag: '"active-tag"' } }
          )
        }
        if (isActive === "false") {
          return HttpResponse.json(
            {
              items: archiveEvents,
              total: archiveEvents.length,
              limit: 12,
              cursor: null,
              next_cursor: null,
              has_more: false,
            },
            { headers: { ETag: '"archive-tag"' } }
          )
        }
        return HttpResponse.json({
          items: [],
          total: 0,
          limit: 12,
          cursor: null,
          next_cursor: null,
          has_more: false,
        })
      })
    )

    const WrappedEvents = () => (
      <AuthContext.Provider value={authValue}>
        <Events />
      </AuthContext.Provider>
    )

    await renderWithRouter({
      ui: WrappedEvents,
      queryClient,
      authProvider: false,
    })

    expect(await screen.findByText("Active event 1")).toBeInTheDocument()
    expect(activeRequestCount).toBe(1)

    const archiveTab = await screen.findByRole("tab", { name: /past events/i })
    await user.click(archiveTab)

    expect(await screen.findByText("Archived event 1")).toBeInTheDocument()
    expect(screen.queryByText("Active event 1")).not.toBeInTheDocument()

    const activeTab = await screen.findByRole("tab", { name: /upcoming/i })
    await user.click(activeTab)

    await waitFor(() => expect(activeRequestCount).toBe(2))
    expect(await screen.findByText("Active event 1")).toBeInTheDocument()
    expect(screen.queryByText("Archived event 1")).not.toBeInTheDocument()

    queryClient.clear()
  })
})
