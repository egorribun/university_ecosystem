import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { SettingsBackdrop } from "./SettingsBackdrop"

// Wave 193 SW3 — SettingsBackdrop Storybook fixture.
//
// 3-prop family (isNarrow + isMobile + prefersReducedMotion, all optional;
// `dropBlur = prefersReducedMotion || isMobile`). Slate/purple ambient orbs
// (W184 SW6 palette — 4 orbs vs the usual 3, balancing the wider 4-tab
// layout) scoped under `.settings-theme` (tokens/settings.css), so the
// `themed(dark)` factory wraps in `.settings-theme` with `.dark` as an
// ANCESTOR for the dark variant. Production wrapper: Settings.tsx:152.
//
// Variants: Default / DarkMode / Narrow (tablet: narrow orbs, blur KEPT) /
// ReducedMotion / Mobile (phone: blur DROPPED via isMobile).

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="settings-theme relative h-[600px] w-full overflow-hidden"
        style={{ background: "var(--bg-page)" }}
      >
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>Settings surface — slate/purple orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof SettingsBackdrop> = {
  title: "Settings/SettingsBackdrop",
  component: SettingsBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof SettingsBackdrop>

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
