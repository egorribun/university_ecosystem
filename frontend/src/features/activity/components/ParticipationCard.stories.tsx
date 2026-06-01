import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { ParticipationStats } from "../types"
import { ParticipationCard } from "./ParticipationCard"

// Wave 198 SW5 — ParticipationCard Storybook fixture (activity card, pure-props).
//
// CardShell + AnimatedRing (count toward goal) + TrendChip + SkeletonMorph. The
// `separator` prop joins the hours/groups summary. No network. m.* → LazyMotion;
// `.activity-theme` for tokens.
//
// Variants: Default / Loading / DarkMode.

const PARTICIPATION: ParticipationStats = {
  events: 7,
  hours: 24,
  groups: 3,
  goal: 10,
  trend: 1,
  recent: [
    { title: "Hackathon 2026", date: "2026-05-27", role: "Participant" },
    { title: "Robotics Club", date: "2026-05-22", role: "Member" },
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

const meta: Meta<typeof ParticipationCard> = {
  title: "Activity/ParticipationCard",
  component: ParticipationCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { participation: PARTICIPATION, hasInitiallyLoaded: true, separator: " · ", ringSize: 88 },
}

export default meta
type Story = StoryObj<typeof ParticipationCard>

export const Default: Story = {
  decorators: [themed(false)],
}

export const Loading: Story = {
  args: { hasInitiallyLoaded: false },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
