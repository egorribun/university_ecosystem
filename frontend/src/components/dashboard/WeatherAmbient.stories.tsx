import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { WeatherAmbient } from "./WeatherAmbient"

const meta: Meta<typeof WeatherAmbient> = {
  title: "Dashboard/WeatherAmbient",
  component: WeatherAmbient,
  parameters: {
    layout: "fullscreen",
  },
  decorators: [
    (Story) => (
      <div className="relative w-full h-[400px] bg-slate-900 overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center text-white/20 font-bold pointer-events-none">
          Background Preview (Dark)
        </div>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof WeatherAmbient>

export const Drizzle: Story = {
  args: {
    animation: "drizzle",
  },
}

export const Snow: Story = {
  args: {
    animation: "snow",
  },
}

export const Storm: Story = {
  args: {
    animation: "storm",
  },
}

export const Disabled: Story = {
  args: {
    animation: "storm",
    disabled: true,
  },
}
