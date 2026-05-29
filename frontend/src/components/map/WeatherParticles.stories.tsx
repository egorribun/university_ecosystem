import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { WeatherParticles } from "./WeatherParticles"

// Wave 199 SW1 — WeatherParticles story (CONTEXT-tier, no infra).
//
// Canvas particle overlay for the campus map. Self-contained: a ResizeObserver
// sizes the canvas to its container + a rAF loop draws rain/snow/storm/fog from
// the `condition` prop (returns null for clear/cloudy + prefers-reduced-motion).
// No network, no portal, no framer-motion. The harness gives the absolute-inset
// overlay a sized `relative` container with a contrasting backdrop so particles
// are visible. Particle positions use Math.random() → Chromatic drift is
// expected (collect-only auto-accepts).
//
// Variants: Rain / Snow / Storm / Fog / DarkRain.

const framed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        style={{
          position: "relative",
          width: 480,
          height: 320,
          overflow: "hidden",
          borderRadius: 12,
          background: dark ? "#1e293b" : "#dbeafe",
        }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof WeatherParticles> = {
  title: "Map/WeatherParticles",
  component: WeatherParticles,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { condition: "rain", isDark: false },
}

export default meta
type Story = StoryObj<typeof WeatherParticles>

export const Rain: Story = { args: { condition: "rain" }, decorators: [framed(false)] }

export const Snow: Story = { args: { condition: "snow" }, decorators: [framed(false)] }

export const Storm: Story = { args: { condition: "storm" }, decorators: [framed(false)] }

export const Fog: Story = { args: { condition: "fog" }, decorators: [framed(false)] }

export const DarkRain: Story = {
  args: { condition: "rain", isDark: true },
  decorators: [framed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
