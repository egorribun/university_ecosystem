import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "ru", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/app/logger", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/app/logger")>()),
  logError: vi.fn(),
}))

// Configure the real generated singleton with production Axios/interceptors.
// Do not mock the API wrapper, SDK, either dialog, or the creation callback.
import "@/api/client"
import { createEvent, type CreateEventPayload } from "@/api/events"
import { CampusTimezoneProvider } from "@/contexts/CampusTimezoneContext"
import { EventFormDialog } from "@/features/events/components/EventFormDialog"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { server } from "@/tests/mocks/server"

function rejectEventPosts() {
  const requests: unknown[] = []
  server.use(
    http.post("*/api/v1/events", async ({ request }) => {
      requests.push(await request.json())
      return HttpResponse.text("Controlled event-create failure", { status: 500 })
    })
  )
  return requests
}

// Existing TextField labels have no associated id; use their real wrapper.
function fieldByLabel(labelText: string): HTMLElement {
  const label = screen.getAllByText(labelText).find((element) => element.tagName === "LABEL")
  const field = label?.parentElement?.querySelector("input, textarea")
  if (!(field instanceof HTMLElement)) throw new Error("Expected event draft field")
  return field
}

describe("event creation through the real HTTP client", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    acceptBrowserSessionGeneration()
  })

  it("rejects a real HTTP failure instead of resolving an absent event", async () => {
    const requests = rejectEventPosts()
    const draft: CreateEventPayload = {
      title: "HTTP boundary event",
      location: "Campus hall",
      starts_at: "2026-12-01T10:00:00Z",
      ends_at: "2026-12-01T11:00:00Z",
    }

    const settlement = await createEvent(draft).then(
      (value) => ({ status: "fulfilled" as const, value }),
      (error: unknown) => ({ status: "rejected" as const, error })
    )

    // A canceled preflight or invalid fixture must not count as target RED.
    expect(requests).toHaveLength(1)
    expect(requests[0]).toMatchObject(draft)
    expect(settlement).toMatchObject({
      status: "rejected",
      error: { response: { status: 500 } },
    })
  })

  it("keeps the composed dialog draft when the real create request fails", async () => {
    const requests = rejectEventPosts()
    const onClose = vi.fn()
    const onSuccess = vi.fn()
    const user = userEvent.setup()

    render(
      <CampusTimezoneProvider timeZone="UTC">
        <EventFormDialog open language="ru" onClose={onClose} onSuccess={onSuccess} />
      </CampusTimezoneProvider>
    )
    await user.type(fieldByLabel("events:form.title"), "Retry event creation")
    await user.type(fieldByLabel("events:form.location"), "Campus hall")
    fireEvent.change(fieldByLabel("events:form.start"), {
      target: { value: "2026-12-01T10:00" },
    })
    fireEvent.change(fieldByLabel("events:form.end"), {
      target: { value: "2026-12-01T11:00" },
    })
    const submit = screen.getByRole("button", { name: "common:buttons.create" })
    expect(submit).toBeEnabled()
    await user.click(submit)

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(requests[0]).toMatchObject({
      title: "Retry event creation",
      location: "Campus hall",
      starts_at: expect.stringMatching(/^2026-12-01T10:00:00(?:\.000)?Z$/),
      ends_at: expect.stringMatching(/^2026-12-01T11:00:00(?:\.000)?Z$/),
    })
    // Both the faulty close path and the corrected error path can settle.
    await waitFor(() => {
      expect(screen.queryByRole("alert") !== null || onClose.mock.calls.length > 0).toBe(true)
    })
    expect(onClose).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(fieldByLabel("events:form.title")).toHaveValue("Retry event creation")
    expect(fieldByLabel("events:form.location")).toHaveValue("Campus hall")
    expect(fieldByLabel("events:form.start")).toHaveValue("2026-12-01T10:00")
    expect(fieldByLabel("events:form.end")).toHaveValue("2026-12-01T11:00")
    expect(screen.getByRole("alert")).toHaveTextContent("common:errors.generic")
    expect(submit).toBeEnabled()
  })
})
