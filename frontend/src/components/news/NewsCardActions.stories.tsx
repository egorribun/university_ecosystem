import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { NewsCardActions } from "./NewsCardActions"

// Wave 197 SW1 — NewsCardActions Storybook fixture (CONTEXT-tier, cheap/ambient).
//
// Admin overflow menu (edit / delete) for a news card. The trigger is absolutely
// positioned (top-right), so the decorator supplies a sized `relative` card host.
// Menu open/close is internal state; the resting render is the 3-dot trigger.
// Labels via the global I18nextProvider.
//
// Variants: Default / Disabled.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div
          className="relative overflow-hidden rounded-2xl border border-glass-border bg-surface"
          style={{ width: 320, height: 160 }}
        >
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsCardActions> = {
  title: "News/NewsCardActions",
  component: NewsCardActions,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    id: "n1",
    onEdit: () => {},
    onDelete: () => {},
  },
}

export default meta
type Story = StoryObj<typeof NewsCardActions>

export const Default: Story = {
  decorators: [themed(false)],
}

export const Disabled: Story = {
  args: { isDisabled: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
