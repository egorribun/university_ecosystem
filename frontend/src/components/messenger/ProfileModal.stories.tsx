import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { User } from "@/types/User"
import { ProfileModal } from "./ProfileModal"

// Wave 197 SW3 — ProfileModal Storybook fixture (CONTEXT-tier, cheap/ambient).
//
// Messenger profile dialog: avatar + name + status. Opens when any of
// user/loading/error is truthy (`fixed inset-0` overlay — inline, NOT a portal,
// so the .dark/.messenger-theme wrapper themes it). Uses framer-motion `m.*` →
// needs <LazyMotion features={domAnimation}> (preview has no global LazyMotion).
//
// Variants: WithUser / Loading / ErrorState / DarkMode.

const SAMPLE_USER: User = {
  id: "u1",
  email: "e.ivanova@guu.ru",
  full_name: "Dr. Elena Ivanova",
  role: "teacher",
  is_active: true,
  avatar_url: "https://i.pravatar.cc/150?img=47",
  avatar_url_optimized: null,
  cover_url_optimized: null,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div
          className="messenger-theme"
          style={{ background: "var(--bg-page)", minHeight: "100vh" }}
        >
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof ProfileModal> = {
  title: "Messenger/ProfileModal",
  component: ProfileModal,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: { onClose: () => {} },
}

export default meta
type Story = StoryObj<typeof ProfileModal>

export const WithUser: Story = {
  args: { user: SAMPLE_USER, loading: false, error: null },
  decorators: [themed(false)],
}

export const Loading: Story = {
  args: { user: null, loading: true, error: null },
  decorators: [themed(false)],
}

export const ErrorState: Story = {
  args: { user: null, loading: false, error: "Could not load this profile. Please try again." },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { user: SAMPLE_USER, loading: false, error: null },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
