import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { User } from "@/types/User"
import { NewChatModal } from "./NewChatModal"

// Wave 198 SW1 — NewChatModal Storybook fixture (CONTEXT-tier; ex-"A" card).
//
// No module mocking needed: the /users search useQuery is `enabled: open &&
// debouncedSearch.length > 1`, i.e. idle until the user types. So the base story
// (open + empty search) makes ZERO network calls and renders the modal chrome +
// search box cleanly. The modal is `fixed inset-0` (NOT createPortal) and does NOT
// call useMessenger(), so it just needs the ambient providers + LazyMotion (m.*) +
// the `.messenger-theme` scope for its CSS tokens (`.messenger-card-matte`, etc.).
//
// WithResults seeds a per-story QueryClient at ["users", ""] (the initial empty
// debouncedSearch key). enabled:false still serves cached data, so the listbox
// renders the user rows — a way to demonstrate the row UI without a service worker.
//
// Variants: Default (empty) / WithResults (seeded) / DarkMode.

const noop = () => {}

const USERS = [
  { id: "u1", full_name: "Alice Anderson", email: "alice@university.dev", avatar_url: null },
  { id: "u2", full_name: "Bob Brown", email: "bob@university.dev", avatar_url: null },
  { id: "u3", full_name: "Carol Chen", email: "carol@university.dev", avatar_url: null },
] as unknown as User[]

const seededClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
seededClient.setQueryData(["users", ""], USERS)

const seededClientDecorator: Decorator = (Story) => (
  <QueryClientProvider client={seededClient}>
    <Story />
  </QueryClientProvider>
)

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="messenger-theme" style={{ minHeight: 600, position: "relative" }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof NewChatModal> = {
  title: "Messenger/NewChatModal",
  component: NewChatModal,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: { open: true, onClose: noop, onSelect: noop },
}

export default meta
type Story = StoryObj<typeof NewChatModal>

export const Default: Story = {
  decorators: [themed(false)],
}

export const WithResults: Story = {
  decorators: [themed(false), seededClientDecorator],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
