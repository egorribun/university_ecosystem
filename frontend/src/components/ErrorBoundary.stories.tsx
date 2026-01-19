import type { Meta, StoryObj } from "@storybook/react-vite"
import { ErrorBoundary } from "./ErrorBoundary"
import { fn } from "storybook/test"

// Component that throws an error for testing
function ErrorThrowingComponent(): React.ReactNode {
  throw new Error("Test error for Storybook demonstration")
}

function StableChildComponent() {
  return (
    <div className="p-4 border rounded-lg border-green-500/30 bg-green-500/10">
      <p className="text-green-400">✓ This component is working correctly</p>
    </div>
  )
}

const meta: Meta<typeof ErrorBoundary> = {
  title: "Components/ErrorBoundary",
  component: ErrorBoundary,
  tags: ["autodocs"],
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "Error boundary component that catches JavaScript errors in child components and displays a fallback UI with retry, reload, and go home actions.",
      },
    },
  },
  argTypes: {
    onError: {
      action: "error-caught",
      description: "Callback when an error is caught",
    },
    fallback: {
      description: "Custom fallback UI to display when an error occurs",
    },
  },
}

export default meta
type Story = StoryObj<typeof ErrorBoundary>

export const NoError: Story = {
  args: {
    children: <StableChildComponent />,
    onError: fn(),
  },
  parameters: {
    docs: {
      description: {
        story: "Normal state when children render without errors.",
      },
    },
  },
}

export const WithError: Story = {
  args: {
    children: <ErrorThrowingComponent />,
    onError: fn(),
  },
  parameters: {
    docs: {
      description: {
        story:
          "Error state showing the default fallback UI with retry, reload, and go home buttons.",
      },
    },
  },
}

export const CustomFallback: Story = {
  args: {
    children: <ErrorThrowingComponent />,
    fallback: (
      <div className="flex min-h-[300px] items-center justify-center bg-red-500/10 p-8">
        <div className="text-center">
          <span className="text-4xl" role="img" aria-label="error">
            💥
          </span>
          <h2 className="mt-4 text-xl font-bold text-red-400">Custom Error UI</h2>
          <p className="mt-2 text-red-300/70">This is a custom fallback component.</p>
        </div>
      </div>
    ),
    onError: fn(),
  },
  parameters: {
    docs: {
      description: {
        story: "Using a custom fallback component instead of the default error UI.",
      },
    },
  },
}
