import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { SkeletonMorph } from "./SkeletonMorph"

const sampleSkeleton = <div className="h-32 w-full animate-pulse rounded-xl bg-input-mix" />
const sampleContent = (
  <div className="flex h-32 w-full items-center justify-center rounded-xl bg-brand/(--opacity-subtle) font-bold text-text-primary">
    Loaded content
  </div>
)

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 360, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof SkeletonMorph> = {
  title: "UI/SkeletonMorph",
  component: SkeletonMorph,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof SkeletonMorph>

export const Loading: Story = {
  args: { loaded: false, skeleton: sampleSkeleton, children: sampleContent },
  decorators: [themed(false)],
  parameters: { docs: { description: { story: "Skeleton placeholder while `loaded` is false." } } },
}

export const Loaded: Story = {
  args: { loaded: true, skeleton: sampleSkeleton, children: sampleContent },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { loaded: true, skeleton: sampleSkeleton, children: sampleContent },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
