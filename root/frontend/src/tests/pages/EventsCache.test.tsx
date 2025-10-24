import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { HttpResponse, http } from "msw"

import Events from "@/pages/Events"
import { AuthContext } from "@/contexts/AuthContext"
import type { Event } from "@/types/Event"
import { server } from "../mocks/server"

const buildEvent = (id: number, title: string, isActive: boolean): Event => {
  const start = new Date(Date.now() + id * 60 * 60 * 1000)
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
    created_by: 1,
    created_at: new Date().toISOString(),
    is_active: isActive,
    speaker: null,
    image_url: null,
    about: null,
    about_en: null,
    files: [],
    participant_count: 0,
    is_registered: null,
    my_qr_code: null,
  }
}

const authValue = {
  isAuth: true,
  login: vi.fn(),
  logout: vi.fn(),
  user: {
    id: 1,
    email: "user@example.com",
    full_name: "Test User",
    role: "student",
    group_id: null,
    avatar_url: null,
    cover_url: null,
    about: null,
    record_book_number: null,
    status: null,
    institute: null,
    course: null,
    education_level: null,
    track: null,
    program: null,
    telegram: null,
    achievements: null,
    department: null,
    position: null,
    spotify_connected: false,
    spotify_display_name: null,
    spotify_is_connected: null,
    dnd_enabled: false,
    dnd_start: null,
    dnd_end: null,
    is_active: true,
    mfa_required: false,
    mfa_default_method: null,
    mfa_last_verified_at: null,
    mfa_recovery_codes_generated_at: null,
    totp_enrollments: [],
    webauthn_credentials: [],
    recovery_codes: [],
    mfa_challenges: [],
  },
  loading: false,
  setUser: vi.fn(),
  refresh: vi.fn(),
  pendingMfa: null,
  submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
  requireMfa: vi.fn().mockResolvedValue(null),
}

describe("Events caching", () => {
  it("restores cached data when a 304 response is received after switching tabs", async () => {
    const user = userEvent.setup()
    const activeEvents = [buildEvent(1, "Active event 1", true)]
    const archiveEvents = [buildEvent(2, "Archived event 1", false)]
    let activeRequestCount = 0

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
              cursor: 0,
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
              cursor: 0,
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
          cursor: 0,
          next_cursor: null,
          has_more: false,
        })
      })
    )

    render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter>
          <Events />
        </MemoryRouter>
      </AuthContext.Provider>
    )

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
  })
})
