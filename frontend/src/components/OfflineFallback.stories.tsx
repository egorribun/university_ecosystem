import type { Meta, StoryObj } from "@storybook/react-vite"
import { OfflineFallback } from "./OfflineFallback"
import { MemoryRouter } from "react-router-dom"
import { fn } from "@storybook/test"

const meta: Meta<typeof OfflineFallback> = {
  title: "Components/OfflineFallback",
  component: OfflineFallback,
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
  parameters: {
    layout: "fullscreen",
    backgrounds: {
      default: "dark",
    },
    docs: {
      description: {
        component:
          "Offline fallback component displayed when the application detects no network connection. Includes retry and go home actions with animated entrance.",
      },
    },
  },
}

export default meta
type Story = StoryObj<typeof OfflineFallback>

export const Default: Story = {
  args: {},
  parameters: {
    docs: {
      description: {
        story: "Default offline state with retry and go home buttons.",
      },
    },
  },
}

export const WithCustomRetry: Story = {
  args: {
    onRetry: fn(),
  },
  parameters: {
    docs: {
      description: {
        story: "Offline state with a custom onRetry callback for manual retry handling.",
      },
    },
  },
}
