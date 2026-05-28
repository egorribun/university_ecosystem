import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { ActivityTrendChart } from "./ActivityTrendChart"

// Wave 194 SW1 — ActivityTrendChart Storybook fixture.
//
// First non-backdrop story under features/activity/ (discoverable via the
// W193 second glob `../src/features/**`). The component is a custom SVG line
// chart whose trend line draws in via framer-motion `m.polyline` pathLength.
// Props: plain `data: {date,value}[]` + required `ariaLabel` (+ optional
// colorVar/height/formatDate). No context beyond i18n (global preview
// decorator) BUT it renders `.activity-chart-card` + reads `--activity-*`
// tokens scoped under `.activity-theme`, and `m.*` needs a
// `LazyMotion features={domAnimation}` ancestor (preview.tsx provides
// neither — mirror of AppProviders W124 SW1). `pauseAnimationAtEnd` lets
// Chromatic settle the pathLength draw before snapshot.
//
// Variants: Default (7 points), TwoPoints (min length for a line),
// SinglePoint (<2 → `activity:charts.noChartData` fallback), DarkMode.

const trendData = [
  { date: "2026-05-01", value: 72 },
  { date: "2026-05-08", value: 78 },
  { date: "2026-05-15", value: 70 },
  { date: "2026-05-22", value: 85 },
  { date: "2026-05-29", value: 88 },
  { date: "2026-06-05", value: 82 },
  { date: "2026-06-12", value: 91 },
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

const meta: Meta<typeof ActivityTrendChart> = {
  title: "Features/Activity/ActivityTrendChart",
  component: ActivityTrendChart,
  parameters: {
    layout: "fullscreen",
    chromatic: { pauseAnimationAtEnd: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ActivityTrendChart>

export const Default: Story = {
  args: {
    data: trendData,
    ariaLabel: "Attendance trend over the last seven weeks",
  },
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story:
          "7-point attendance trend. The m.polyline draws in via pathLength 0→1 (settled for Chromatic via pauseAnimationAtEnd). The gradient area fill uses a useId-unique gradient id per FIX-86-02.",
      },
    },
  },
}

export const TwoPoints: Story = {
  args: {
    data: [
      { date: "2026-06-05", value: 64 },
      { date: "2026-06-12", value: 90 },
    ],
    ariaLabel: "Attendance trend across two data points",
  },
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story: "Minimum length (2 points) that still renders a line rather than the fallback.",
      },
    },
  },
}

export const SinglePoint: Story = {
  args: {
    data: [{ date: "2026-06-12", value: 88 }],
    ariaLabel: "Attendance trend with insufficient data",
  },
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story:
          "data.length < 2 renders the `activity:charts.noChartData` fallback card (no SVG drawn).",
      },
    },
  },
}

export const DarkMode: Story = {
  args: {
    data: trendData,
    ariaLabel: "Attendance trend over the last seven weeks",
  },
  decorators: [themed(true)],
  parameters: {
    backgrounds: { default: "dark" },
  },
}
