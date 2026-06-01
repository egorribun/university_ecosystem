import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { GradeStats } from "../types"
import { GradesCard } from "./GradesCard"

// Wave 198 SW5 — GradesCard Storybook fixture (activity card, pure-props).
//
// CardShell + AnimatedRing (gauge) + TrendChip + SkeletonMorph. The label format
// switches on `grades.scale` ("5" | "100" | "gpa"). No network. m.* → LazyMotion;
// `.activity-theme` for tokens.
//
// Variants: FivePoint / HundredPoint / Gpa / DarkMode.

const FIVE: GradeStats = {
  average: 4.6,
  scale: "5",
  trend: 2,
  recent: [
    { course: "Calculus", score: 5, max: 5, date: "2026-05-28" },
    { course: "Physics", score: 4, max: 5, date: "2026-05-26" },
  ],
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="activity-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div className="activity-card-matte" style={{ width: 420 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof GradesCard> = {
  title: "Activity/GradesCard",
  component: GradesCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { grades: FIVE, hasInitiallyLoaded: true, ringSize: 88 },
}

export default meta
type Story = StoryObj<typeof GradesCard>

export const FivePoint: Story = {
  decorators: [themed(false)],
}

export const HundredPoint: Story = {
  args: { grades: { average: 87, scale: "100", trend: -2, recent: [] } },
  decorators: [themed(false)],
}

export const Gpa: Story = {
  args: { grades: { average: 3.72, scale: "gpa", trend: 1, recent: [] } },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
