import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { useTranslation } from "react-i18next"
import { MobileDrawerProfile } from "./MobileDrawerProfile"
import type { User } from "@/types/User"

const baseUser = {
  id: "u-1",
  full_name: "Anna Petrova",
  email: "anna@guu.ru",
  role: "student",
  avatar_url: "https://i.pravatar.cc/96?img=5",
  avatar_updated_at: null,
  avatar_version: null,
  updated_at: "2026-05-01T00:00:00Z",
} as unknown as User

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 360 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

/** Harness supplies the real i18next `t` from the preview I18nextProvider. */
function ProfileHarness({ user }: { user: User }) {
  const { t } = useTranslation()
  return <MobileDrawerProfile user={user} onProfileClick={() => {}} t={t} />
}

const meta: Meta<typeof MobileDrawerProfile> = {
  title: "Navbar/MobileDrawerProfile",
  component: MobileDrawerProfile,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof MobileDrawerProfile>

export const Student: Story = {
  render: () => <ProfileHarness user={baseUser} />,
  decorators: [themed(false)],
}

export const Admin: Story = {
  render: () => <ProfileHarness user={{ ...baseUser, role: "admin" } as unknown as User} />,
  decorators: [themed(false)],
  parameters: { docs: { description: { story: "Admin role pill instead of student." } } },
}

export const DarkMode: Story = {
  render: () => <ProfileHarness user={baseUser} />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
