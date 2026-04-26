import type { Meta, StoryObj } from "@storybook/react-vite"
import { ContentSummary } from "./ContentSummary"

const meta: Meta<typeof ContentSummary> = {
  title: "UI/ContentSummary",
  component: ContentSummary,
  tags: ["autodocs"],
  argTypes: {
    loading: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof ContentSummary>

export const Default: Story = {
  args: {
    summary:
      "This is an AI-generated summary of the content below. It highlights the key takeaways and provides a quick overview for the user.",
    loading: false,
    children: (
      <div className="rounded-lg border border-subtle p-4 text-sm text-text-primary">
        <p>
          This is the full content that was summarized. It contains much more detail and
          background information that the user can explore if they are interested in
          learning more after reading the summary.
        </p>
        <p className="mt-2">
          Additional paragraphs of detailed information would go here, explaining the
          nuances and specifics of the topic at hand.
        </p>
      </div>
    ),
  },
}

export const Loading: Story = {
  args: {
    ...Default.args,
    loading: true,
  },
}

export const NoSummary: Story = {
  args: {
    ...Default.args,
    summary: null,
  },
}
