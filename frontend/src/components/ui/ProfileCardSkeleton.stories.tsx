import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { ProfileCardSkeleton } from "./ProfileCardSkeleton"

// Wave 198 SW3 — ProfileCardSkeleton Storybook fixture (shimmer; `showCover?`).
//
// Loading placeholder for the Profile header (cover + avatar + name + bio + stats).
// Pure visual — Skeleton primitives + global skeleton tokens; useTranslation drives
// the aria-label (ambient i18n). Scoped in `.profile-theme`.
//
// Variants: Default / NoCover / DarkMode.

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

const meta: Meta<typeof ProfileCardSkeleton> = {
  title: "Profile/ProfileCardSkeleton",
  component: ProfileCardSkeleton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { showCover: true },
}

export default meta
type Story = StoryObj<typeof ProfileCardSkeleton>

export const Default: Story = {
  decorators: [themed(false)],
}

export const NoCover: Story = {
  args: { showCover: false },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
