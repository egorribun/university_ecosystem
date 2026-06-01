import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { ProfileBackdrop } from "./ProfileBackdrop"

// Wave 193 SW3 — ProfileBackdrop Storybook fixture.
//
// 3-prop family (isNarrow + isMobile + prefersReducedMotion, all optional;
// `dropBlur = prefersReducedMotion || isMobile`). Rose/pink/amber ambient
// orbs (W184 SW5 palette) scoped under `.profile-theme` (tokens/profile.css),
// so the `themed(dark)` factory wraps in `.profile-theme` with `.dark` as an
// ANCESTOR for the dark variant. Production wrapper: Profile.tsx:238.
//
// Variants: Default / DarkMode / Narrow (tablet: narrow orbs, blur KEPT) /
// ReducedMotion / Mobile (phone: blur DROPPED via isMobile).

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="profile-theme relative h-[600px] w-full overflow-hidden"
        style={{ background: "var(--bg-page)" }}
      >
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>Profile surface — rose/pink orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof ProfileBackdrop> = {
  title: "Profile/ProfileBackdrop",
  component: ProfileBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ProfileBackdrop>

export const Default: Story = {
  args: {
    isNarrow: false,
    isMobile: false,
    prefersReducedMotion: false,
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: {
    isNarrow: false,
    isMobile: false,
    prefersReducedMotion: false,
  },
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [themed(true)],
}

export const Narrow: Story = {
  args: {
    isNarrow: true,
    isMobile: false,
    prefersReducedMotion: false,
  },
  parameters: {
    viewport: {
      defaultViewport: "mobile1",
    },
  },
  decorators: [themed(false)],
}

export const ReducedMotion: Story = {
  args: {
    isNarrow: false,
    isMobile: false,
    prefersReducedMotion: true,
  },
  decorators: [themed(false)],
}

export const Mobile: Story = {
  args: {
    isNarrow: true,
    isMobile: true,
    prefersReducedMotion: false,
  },
  parameters: {
    viewport: {
      defaultViewport: "mobile1",
    },
  },
  decorators: [themed(false)],
}
