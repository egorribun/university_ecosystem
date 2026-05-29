import type { Meta, StoryObj } from "@storybook/react-vite"
import ParticleAuthBackground from "./ParticleAuthBackground"

const meta: Meta<typeof ParticleAuthBackground> = {
  title: "UI/ParticleAuthBackground",
  component: ParticleAuthBackground,
  parameters: {
    layout: "fullscreen",
    // W201: 1000-particle canvas swarm (continuous, no VITE_E2E gate in Storybook) → skip snapshot.
    chromatic: { disableSnapshot: true },
    backgrounds: {
      default: "dark",
    },
  },
}

export default meta
type Story = StoryObj<typeof ParticleAuthBackground>

export const Default: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-background overflow-hidden">
      <ParticleAuthBackground />
      <div className="relative z-10 flex h-full items-center justify-center">
        <div className="rounded-2xl bg-glass p-12 backdrop-blur-xl border border-glass-border shadow-premium">
          <h1 className="text-4xl font-black text-text-primary">Premium Login</h1>
          <p className="mt-4 text-text-secondary">Hover around to see the swarm effect.</p>
        </div>
      </div>
    </div>
  ),
}
