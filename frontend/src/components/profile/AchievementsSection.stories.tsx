import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { AchievementsSection } from "./AchievementsSection"
import type { AchievementItem } from "./profileUtils"

const achievements: AchievementItem[] = [
  { key: "a1", name: "Dean's List 2025", issuer: "Academic Board" },
  { key: "a2", name: "Hackathon Winner", issuer: "GUU Tech Club" },
  { key: "a3", name: "Research Grant", issuer: "Ministry of Science" },
  { key: "a4", name: "Volunteer of the Year", issuer: "Student Union" },
] as AchievementItem[]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ maxWidth: 640, margin: "0 auto" }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof AchievementsSection> = {
  title: "Profile/AchievementsSection",
  component: AchievementsSection,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof AchievementsSection>

export const Default: Story = {
  args: { achievements, onAchievementClick: () => {} },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { achievements, onAchievementClick: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
