import type { Meta, StoryObj } from "@storybook/react-vite"
import LoadingState from "./LoadingState"
import { MemoryRouter } from "react-router-dom"

const meta: Meta<typeof LoadingState> = {
  title: "Components/LoadingState",
  component: LoadingState,
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
    docs: {
      description: {
        component:
          "Full-page loading state component with skeleton header and centered spinner. Used for page-level loading transitions.",
      },
    },
  },
  argTypes: {
    label: {
      control: "text",
      description: "Custom loading message (defaults to translated 'Loading...')",
    },
  },
}

export default meta
type Story = StoryObj<typeof LoadingState>

export const Default: Story = {
  args: {},
  parameters: {
    docs: {
      description: {
        story: "Default loading state with translated loading message.",
      },
    },
  },
}

export const CustomLabel: Story = {
  args: {
    label: "Загрузка данных...",
  },
  parameters: {
    docs: {
      description: {
        story: "Loading state with a custom message.",
      },
    },
  },
}

export const LoadingEvents: Story = {
  args: {
    label: "Загрузка мероприятий...",
  },
  parameters: {
    docs: {
      description: {
        story: "Loading state shown when fetching events.",
      },
    },
  },
}

export const LoadingProfile: Story = {
  args: {
    label: "Загрузка профиля...",
  },
  parameters: {
    docs: {
      description: {
        story: "Loading state shown when fetching user profile.",
      },
    },
  },
}




