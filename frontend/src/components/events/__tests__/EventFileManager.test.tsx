import { render, screen } from "@testing-library/react"
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

import { EventFileManager } from "@/components/events/EventFileManager"
import type { Event } from "@/types/Event"

const baseEvent: Event = {
  id: "evt-1",
  title: "React 19 Patterns Workshop",
  title_en: "React 19 Patterns Workshop",
  starts_at: "2026-06-15T14:00:00Z",
  ends_at: "2026-06-15T16:00:00Z",
  created_by: "admin-1",
  created_at: "2026-05-01T10:00:00Z",
  is_active: true,
  image_url_optimized: null,
  files: [
    {
      id: "f1",
      event_id: "evt-1",
      file_url: "/media/lecture-slides.pdf",
      description: "Lecture slides.pdf",
    },
    {
      id: "f2",
      event_id: "evt-1",
      file_url: "/media/reading-list.pdf",
      description: "Reading list.pdf",
    },
  ],
}

const baseProps = {
  event: baseEvent,
  canEdit: true,
  onUpdate: vi.fn(() => Promise.resolve()),
  onError: vi.fn(),
  onSuccess: vi.fn(),
}

describe("EventFileManager", () => {
  it("renders the file list and upload form when editable", () => {
    render(<EventFileManager {...baseProps} />)
    expect(screen.getByText("events:detail.sections.files.title")).toBeInTheDocument()
    expect(screen.getByText("Lecture slides.pdf")).toBeInTheDocument()
    expect(screen.getByText("Reading list.pdf")).toBeInTheDocument()
    expect(screen.getByText("events:detail.sections.files.pickFile")).toBeInTheDocument()
    expect(screen.getAllByLabelText("events:detail.sections.files.deleteAria")).toHaveLength(2)
  })

  it("hides the upload form and delete buttons when not editable", () => {
    render(<EventFileManager {...baseProps} canEdit={false} />)
    expect(screen.queryByText("events:detail.sections.files.pickFile")).not.toBeInTheDocument()
    expect(
      screen.queryByLabelText("events:detail.sections.files.deleteAria")
    ).not.toBeInTheDocument()
    expect(screen.getByText("Lecture slides.pdf")).toBeInTheDocument()
  })

  it("renders the empty state when there are no files", () => {
    render(<EventFileManager {...baseProps} event={{ ...baseEvent, files: [] }} />)
    expect(screen.getByText("events:detail.sections.files.empty")).toBeInTheDocument()
    expect(screen.queryByText("events:detail.sections.files.title")).not.toBeInTheDocument()
  })
})
