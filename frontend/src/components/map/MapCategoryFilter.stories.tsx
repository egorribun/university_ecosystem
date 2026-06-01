import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { MapCategoryFilter } from "./MapCategoryFilter"

// Wave 196 SW1 — MapCategoryFilter Storybook fixture (LEAF tier batch 2).
//
// Category chip row (role="radiogroup" + aria-checked), mirroring the events
// page category filter. Renders from `active` + `onChange` props alone; chip
// labels come from the global I18nextProvider. No framer-motion → no LazyMotion.
// `.map-theme` supplies the `.map-category-chip` token values.
//
// Variants: AllActive / StudyActive / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="map-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof MapCategoryFilter> = {
  title: "Map/MapCategoryFilter",
  component: MapCategoryFilter,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MapCategoryFilter>

export const AllActive: Story = {
  args: { active: "all", onChange: () => {} },
  decorators: [themed(false)],
}

export const StudyActive: Story = {
  args: { active: "study", onChange: () => {} },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { active: "sports", onChange: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
