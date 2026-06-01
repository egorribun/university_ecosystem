import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { type ComponentProps, useRef } from "react"
import type { User } from "@/types/User"
import { ProfileHeader } from "./ProfileHeader"

// Wave 198 SW6 — ProfileHeader Storybook fixture (profile, pure-props).
//
// Hero cover + avatar + stats + contact buttons + vCard QR (QRCodeSVG, aria-hidden
// per W120 polish-v2). All ~17 props are simple values/callbacks; the two button
// refs come from a useRef harness. SmartImage falls back to bundled assets (no
// network dependency). No m.*. Scoped in `.profile-theme`.
//
// Variants: Default (online + telegram) / Offline / DarkMode.

const USER = {
  full_name: "Alice Anderson",
  email: "alice@university.dev",
  avatar_url: null,
  cover_url: null,
  profile_detail: { status: "MSc Computer Science", telegram: "@alice" },
  education_path: { course: "2", record_book_number: "21-1042" },
} as unknown as User

type HarnessProps = Omit<
  ComponentProps<typeof ProfileHeader>,
  "emailButtonRef" | "telegramButtonRef"
>
function ProfileHeaderHarness(props: HarnessProps) {
  const emailRef = useRef<HTMLButtonElement>(null)
  const telegramRef = useRef<HTMLButtonElement>(null)
  return <ProfileHeader {...props} emailButtonRef={emailRef} telegramButtonRef={telegramRef} />
}

const noop = () => {}
const VCARD = "BEGIN:VCARD\nVERSION:3.0\nFN:Alice Anderson\nEMAIL:alice@university.dev\nEND:VCARD"

const baseProps: HarnessProps = {
  user: USER,
  avatarVersion: 0,
  coverVersion: 0,
  coverParallax: 0,
  coverScale: 1,
  avatarSize: "120px",
  heroPaddingBottom: "84px",
  isOnline: true,
  statusOffset: 8,
  statusSize: 16,
  onEmailClick: noop,
  onTelegramClick: noop,
  onQrClick: noop,
  vCardData: VCARD,
  reduceMotion: false,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="profile-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ width: 420 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof ProfileHeader> = {
  title: "Profile/ProfileHeader",
  component: ProfileHeader,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ProfileHeader>

export const Default: Story = {
  render: () => <ProfileHeaderHarness {...baseProps} />,
  decorators: [themed(false)],
}

export const Offline: Story = {
  render: () => <ProfileHeaderHarness {...baseProps} isOnline={false} />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <ProfileHeaderHarness {...baseProps} />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
