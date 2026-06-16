import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/api/events", () => ({ uploadEventImage: vi.fn(() => Promise.resolve("")) }))

import { EventDetailEditDialog } from "@/components/events/EventDetailEditDialog"
import type { Event } from "@/types/Event"

const baseEvent: Event = {
  id: "evt-1",
  title: "React 19 Patterns Workshop",
  title_en: "React 19 Patterns Workshop",
  description: "A hands-on deep dive into React 19 concurrent features.",
  location: "ГУК-305",
  event_type: "workshop",
  starts_at: "2026-06-15T14:00:00Z",
  ends_at: "2026-06-15T16:00:00Z",
  created_by: "u1",
  created_at: "2026-05-01T10:00:00Z",
  is_active: true,
  speaker: "Dr. Ivanova",
  image_url: "https://picsum.photos/seed/event-detail-edit/800/400",
  image_url_optimized: null,
}

const baseProps = {
  open: true,
  onClose: vi.fn(),
  event: baseEvent,
  onSuccess: vi.fn(),
  onError: vi.fn(),
}

function renderDialog(props = baseProps) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <EventDetailEditDialog {...props} />
    </QueryClientProvider>
  )
}

describe("EventDetailEditDialog", () => {
  it("renders the edit dialog when open", () => {
    renderDialog()
    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeInTheDocument()
    expect(dialog.querySelectorAll("input,textarea").length).toBeGreaterThan(0)
  })

  it("does not render the dialog when closed", () => {
    renderDialog({ ...baseProps, open: false })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("fires onClose when the cancel button is clicked", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderDialog({ ...baseProps, onClose })
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
