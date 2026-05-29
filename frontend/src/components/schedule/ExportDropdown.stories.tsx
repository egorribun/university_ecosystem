import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { ExportDropdown } from "./ExportDropdown"

// Wave 196 SW1 — ExportDropdown Storybook fixture (LEAF tier batch 2).
//
// Schedule multi-format export menu (PDF / PNG / Google Calendar). The menu
// opens on click via internal state, so the static story shows the trigger
// button in its closed state. Uses framer-motion `m.div` inside AnimatePresence
// → LazyMotion decorator (preview.tsx has no global LazyMotion). `.schedule-theme`
// supplies the `.sched-export-dropdown` / `.sched-matte-card` token values.
//
// Variants: Default (idle trigger) / Exporting (spinner) / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="schedule-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof ExportDropdown> = {
  title: "Schedule/ExportDropdown",
  component: ExportDropdown,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ExportDropdown>

export const Default: Story = {
  args: { isExporting: false },
  decorators: [themed(false)],
}

export const Exporting: Story = {
  args: { isExporting: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { isExporting: false },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
