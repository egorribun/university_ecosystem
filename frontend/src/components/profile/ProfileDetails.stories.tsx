import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { ProfileDetails } from "./ProfileDetails"
import type { User } from "@/types/User"

const studentUser = {
  id: "u-1",
  full_name: "Anna Petrova",
  email: "anna@guu.ru",
  role: "student",
  education_path: {
    institute: "Institute of Information Systems",
    education_level: "Bachelor",
    track: "Applied Informatics",
    program: "Software Engineering",
  },
  profile_detail: {
    about: "Third-year student focused on distributed systems and machine learning.",
  },
} as unknown as User

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 560, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof ProfileDetails> = {
  title: "Profile/ProfileDetails",
  component: ProfileDetails,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof ProfileDetails>

export const Expanded: Story = {
  args: { user: studentUser, isOpen: true, onToggle: () => {} },
  decorators: [themed(false)],
}

export const Collapsed: Story = {
  args: { user: studentUser, isOpen: false, onToggle: () => {} },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { user: studentUser, isOpen: true, onToggle: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
