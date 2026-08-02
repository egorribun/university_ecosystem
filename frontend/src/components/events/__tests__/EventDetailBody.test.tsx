import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { Event } from "@/types/Event"

type ChildProps = {
  event: Event
  language?: "en" | "ru"
  canEdit: boolean
  onUpdate: () => Promise<void>
  onError: (message: string) => void
  onSuccess: (message: string) => void
}

vi.mock("@/components/events/EventAboutEditor", () => ({
  EventAboutEditor: ({ event, language, canEdit, onUpdate, onError, onSuccess }: ChildProps) => (
    <div data-testid="event-about-editor">
      <span>{`${event.id}:${language}:${String(canEdit)}`}</span>
      <button type="button" onClick={() => void onUpdate()}>
        about refresh
      </button>
      <button type="button" onClick={() => onError("about error")}>
        about error
      </button>
      <button type="button" onClick={() => onSuccess("about success")}>
        about success
      </button>
    </div>
  ),
}))

vi.mock("@/components/events/EventFileManager", () => ({
  EventFileManager: ({ event, canEdit, onUpdate, onError, onSuccess }: ChildProps) => (
    <div data-testid="event-file-manager">
      <span>{`${event.id}:${String(canEdit)}`}</span>
      <button type="button" onClick={() => void onUpdate()}>
        files refresh
      </button>
      <button type="button" onClick={() => onError("files error")}>
        files error
      </button>
      <button type="button" onClick={() => onSuccess("files success")}>
        files success
      </button>
    </div>
  ),
}))

import { EventDetailBody } from "@/components/events/EventDetailBody"

const event: Event = {
  id: "event-1",
  title: "Russian event",
  title_en: "English event",
  about: "Описание",
  about_en: "Description",
  starts_at: "2026-06-15T14:00:00Z",
  ends_at: "2026-06-15T16:00:00Z",
  created_by: "admin-1",
  created_at: "2026-05-01T10:00:00Z",
  is_active: true,
  image_url_optimized: null,
  files: [],
}

describe("EventDetailBody", () => {
  it("composes localized editable sections and forwards every callback", () => {
    const onRefresh = vi.fn(() => Promise.resolve())
    const onError = vi.fn()
    const onSuccess = vi.fn()

    const { container } = render(
      <EventDetailBody
        event={event}
        language="ru"
        isAdmin
        onRefresh={onRefresh}
        onError={onError}
        onSuccess={onSuccess}
      />
    )

    expect(container.querySelectorAll("section")).toHaveLength(2)
    expect(screen.getByTestId("event-about-editor")).toHaveTextContent("event-1:ru:true")
    expect(screen.getByTestId("event-file-manager")).toHaveTextContent("event-1:true")

    fireEvent.click(screen.getByRole("button", { name: "about refresh" }))
    fireEvent.click(screen.getByRole("button", { name: "files refresh" }))
    fireEvent.click(screen.getByRole("button", { name: "about error" }))
    fireEvent.click(screen.getByRole("button", { name: "files error" }))
    fireEvent.click(screen.getByRole("button", { name: "about success" }))
    fireEvent.click(screen.getByRole("button", { name: "files success" }))

    expect(onRefresh).toHaveBeenCalledTimes(2)
    expect(onError).toHaveBeenNthCalledWith(1, "about error")
    expect(onError).toHaveBeenNthCalledWith(2, "files error")
    expect(onSuccess).toHaveBeenNthCalledWith(1, "about success")
    expect(onSuccess).toHaveBeenNthCalledWith(2, "files success")
  })

  it("passes the read-only English configuration to both sections", () => {
    render(
      <EventDetailBody
        event={event}
        language="en"
        isAdmin={false}
        onRefresh={() => Promise.resolve()}
        onError={vi.fn()}
        onSuccess={vi.fn()}
      />
    )

    expect(screen.getByTestId("event-about-editor")).toHaveTextContent("event-1:en:false")
    expect(screen.getByTestId("event-file-manager")).toHaveTextContent("event-1:false")
  })
})
