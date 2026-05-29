import type { Meta, StoryObj } from "@storybook/react-vite"
import type { Event } from "@/types/Event"
import { EventDetailEditDialog } from "./EventDetailEditDialog"

// Wave 197 SW2 — EventDetailEditDialog Storybook fixture (CONTEXT-tier).
//
// Detail-page edit dialog: derives an EventEditDraft from the `event` prop and
// renders EventEditDialog. useQueryClient / api / uploadEventImage are
// submit-path only (won't fire without Save), and the ambient QueryClientProvider
// from preview.tsx covers the hook. The Dialog portals to document.body, so it
// shows in the default theme only.
//
// Variants: Default (open with event).

const SAMPLE_EVENT: Event = {
  id: "e1",
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
  participant_count: 42,
  is_registered: false,
}

const meta: Meta<typeof EventDetailEditDialog> = {
  title: "Events/EventDetailEditDialog",
  component: EventDetailEditDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: {
    open: true,
    event: SAMPLE_EVENT,
    onClose: () => {},
    onSuccess: () => {},
    onError: () => {},
  },
}

export default meta
type Story = StoryObj<typeof EventDetailEditDialog>

export const Default: Story = {}
