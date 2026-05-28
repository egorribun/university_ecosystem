import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { ActivityBarChart } from "./ActivityBarChart"

// Wave 194 SW1 — ActivityBarChart Storybook fixture.
//
// Custom SVG horizontal bar chart whose value bars grow in via framer-motion
// `m.rect` width 0→target. Props: `data: {label,value,max?}[]` + required
// `ariaLabel` (+ optional colorVar/title). Same `.activity-theme` + LazyMotion
// decorator as ActivityTrendChart (reads `--activity-grade-accent` +
// `--activity-chart-*` tokens; `m.*` needs LazyMotion). The Default fixture
// mixes graded-out-of-100 + ungraded (no `max`) rows to exercise both label
// formats at BarChart.tsx:132 (`bar.max ? value/max : value.toFixed(1)`) +
// the Number.isFinite NaN guard at :37 (FIX-86-01).
//
// Variants: Default (mixed max-present + max-absent), Empty (fallback),
// DarkMode.

const barData = [
  { label: "Mathematics", value: 88, max: 100 },
  { label: "Physics", value: 72.5, max: 100 },
  { label: "History", value: 4.6 },
  { label: "Chemistry", value: 91, max: 100 },
  { label: "Literature", value: 4.2 },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div
          className="activity-theme"
          style={{ background: "var(--bg-page)", padding: "1.5rem", maxWidth: 520 }}
        >
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof ActivityBarChart> = {
  title: "Features/Activity/ActivityBarChart",
  component: ActivityBarChart,
  parameters: {
    layout: "fullscreen",
    chromatic: { pauseAnimationAtEnd: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ActivityBarChart>

export const Default: Story = {
  args: {
    data: barData,
    ariaLabel: "Grades by subject",
  },
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story:
          "5 subjects mixing graded-out-of-100 (Mathematics/Physics/Chemistry) + ungraded GPA-style rows (History/Literature). Bars grow in via m.rect width 0→target with a per-bar stagger delay.",
      },
    },
  },
}

export const Empty: Story = {
  args: {
    data: [],
    ariaLabel: "Grades by subject (no data)",
  },
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story: "data.length === 0 renders the `activity:charts.noChartData` fallback card.",
      },
    },
  },
}

export const DarkMode: Story = {
  args: {
    data: barData,
    ariaLabel: "Grades by subject",
  },
  decorators: [themed(true)],
  parameters: {
    backgrounds: { default: "dark" },
  },
}
