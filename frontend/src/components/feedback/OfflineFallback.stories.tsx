import type { Meta, StoryObj } from "@storybook/react-vite"
import { OfflineFallback } from "./OfflineFallback"
import { fn } from "storybook/test"

// Wave 115 SW5 — removed the per-story `<MemoryRouter>` decorator. The
// global `.storybook/preview.tsx` decorator now provides a TanStack Router
// context that covers all stories; adding a second router here created a
// nested context that broke `<Link>` navigation semantics.
const meta: Meta<typeof OfflineFallback> = {
  title: "Components/OfflineFallback",
  component: OfflineFallback,
  tags: ["autodocs"],
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
