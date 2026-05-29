import type { Meta, StoryObj } from "@storybook/react-vite"
import type { EventEditDraft } from "@/types/Event"
import { EventEditDialog } from "./EventEditDialog"

// Wave 197 SW2 — EventEditDialog Storybook fixture (CONTEXT-tier, cheap/ambient).
//
// Admin edit dialog for an event (title / location / dates / speaker / image).
// Fully prop-driven (draft + setters + flags). The Dialog portals to
// document.body (outside the story decorator) — like EventQrDialog — so it shows
// in the default theme only; a `.dark` wrapper can't reach the portal.
//
// Variants: Default (open) / Loading (saving) / DateError.

const DRAFT: EventEditDraft = {
  id: "e1",
  title: "React 19 Patterns Workshop",
  title_en: "React 19 Patterns Workshop",
  description: "A hands-on deep dive into React 19 concurrent features and the new compiler.",
  location: "ГУК-305",
  location_en: "Main Building, Room 305",
  event_type: "workshop",
  starts_at: "2026-06-15T14:00",
  ends_at: "2026-06-15T16:00",
  speaker: "Dr. Ivanova",
  image_url: "https://picsum.photos/seed/event-edit/800/400",
}

const meta: Meta<typeof EventEditDialog> = {
  title: "Events/EventEditDialog",
  component: EventEditDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: {
    open: true,
    draft: DRAFT,
    setDraft: () => {},
    onSave: () => {},
    onClose: () => {},
    loading: false,
    imageLoading: false,
    dateError: false,
    normalizedTitle: "React 19 Patterns Workshop",
    normalizedLocation: "ГУК-305",
    newImage: null,
    setNewImage: () => {},
    previewUrl: null,
  },
}

export default meta
type Story = StoryObj<typeof EventEditDialog>

export const Default: Story = {}

export const Loading: Story = {
  args: { loading: true },
}

export const DateError: Story = {
  args: { dateError: true },
}
