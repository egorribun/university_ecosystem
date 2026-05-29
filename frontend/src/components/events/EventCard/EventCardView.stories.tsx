import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { useSpotlight } from "@/components/ui/Spotlight"
import { EventCardView, type EventCardViewProps } from "./EventCardView"

// Wave 197 SW4 — EventCardView Storybook fixture (CONTEXT-tier, complex).
//
// Pattern mirror of NewsCardView: hero + content + spotlight overlay + quick-view
// + admin menu + edit/delete dialogs (lazy via Suspense). Pure presentation; the
// `spotlight` prop comes from the real useSpotlight() hook in a harness, wrapped
// in <LazyMotion features={domAnimation}> for the m.* tree.
//
// Variants: Soon / Live / AdminEnded / DarkMode.

type HarnessProps = Omit<EventCardViewProps, "spotlight">

function EventCardHarness(props: HarnessProps) {
  const spotlight = useSpotlight()
  return <EventCardView {...props} spotlight={spotlight} />
}

const BASE: HarnessProps = {
  id: "e1",
  title: "React 19 Patterns Workshop",
  speaker: "Dr. Ivanova",
  startsAt: "2026-06-15T14:00:00Z",
  endsAt: "2026-06-15T16:00:00Z",
  location: "ГУК-305",
  description: "A hands-on deep dive into React 19 concurrent features and the new compiler.",
  imageUrl: "https://picsum.photos/seed/eventcardview/800/400",
  participantCount: 42,
  isRegistered: false,
  isEnded: false,
  isAdmin: false,
  loading: false,
  error: "",
  hoveringDisabled: false,
  timeStatus: "soon",
  category: "workshop",
  editOpen: false,
  confirmDeleteOpen: false,
  editData: {},
  menuAnchor: null,
  setMenuAnchor: () => {},
  menuId: "event-card-menu-e1",
  onEditOpen: () => {},
  onEditClose: () => {},
  onDeleteOpen: () => {},
  onDeleteClose: () => {},
  onDeleteConfirm: () => {},
  onEditSave: () => {},
  editDraft: {},
  setEditDraft: () => {},
  imageLoading: false,
  newImage: null,
  setNewImage: () => {},
  previewUrl: null,
  onErrorClose: () => {},
  t: {
    deleteTitle: "Delete event?",
    deleteDesc: "This action cannot be undone.",
    confirm: "Delete",
    cancel: "Cancel",
  },
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 380 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof EventCardView> = {
  title: "Events/EventCardView",
  component: EventCardView,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventCardView>

export const Soon: Story = {
  render: () => <EventCardHarness {...BASE} />,
  decorators: [themed(false)],
}

export const Live: Story = {
  render: () => <EventCardHarness {...BASE} timeStatus="live" isRegistered />,
  decorators: [themed(false)],
}

export const AdminEnded: Story = {
  render: () => <EventCardHarness {...BASE} isAdmin isEnded timeStatus="none" />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <EventCardHarness {...BASE} isRegistered timeStatus="live" />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
