import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { ActivityExportButton } from "./ActivityExportButton"

// Wave 196 SW3 — ActivityExportButton Storybook fixture (LEAF tier batch 2).
//
// Export menu (PDF / PNG via lazy html-to-image + jspdf). Renders from a single
// `contentRef` prop; the menu opens on click (internal state) so the static story
// shows the idle trigger. The fixture passes `{ current: null }` — the export
// handlers guard `if (!el) return`, so a null ref is a safe no-op. `.activity-theme`
// supplies `.activity-export-btn` tokens. No framer-motion.
//
// Variants: Default / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="activity-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof ActivityExportButton> = {
  title: "Features/Activity/ActivityExportButton",
  component: ActivityExportButton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ActivityExportButton>

export const Default: Story = {
  args: { contentRef: { current: null } },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { contentRef: { current: null } },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
