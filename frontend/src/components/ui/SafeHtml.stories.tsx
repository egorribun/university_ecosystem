import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import SafeHtml from "./SafeHtml"

// Wave 196 SW2 — SafeHtml Storybook fixture (LEAF tier batch 2).
//
// Renders sanitized HTML via the WASM ammonia sanitizer, with a regex tag-strip
// fallback if the WASM module hasn't initialized (RZ-24-04) and an optional
// `fallback` node for empty output. Renders from props alone (html/className/
// fallback). No framer-motion, no theme scope. Story content is benign demo markup.
//
// Variants: RichHtml / PlainText / WithFallback (empty html → fallback node).

const RICH_HTML =
  "<p>Welcome to the <strong>University Ecosystem</strong> — this is <em>sanitized</em> rich text with a list:</p><ul><li>First item</li><li>Second item</li></ul>"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        style={{ background: "var(--bg-page)", padding: "2rem", maxWidth: 480 }}
        className="text-text-primary"
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof SafeHtml> = {
  title: "UI/SafeHtml",
  component: SafeHtml,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof SafeHtml>

export const RichHtml: Story = {
  args: { html: RICH_HTML, className: "prose-sm space-y-2" },
  decorators: [themed(false)],
}

export const PlainText: Story = {
  args: { html: "Just a plain sentence with no markup." },
  decorators: [themed(false)],
}

export const WithFallback: Story = {
  args: { html: "", fallback: <em className="text-(--text-secondary)">No content available</em> },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { html: RICH_HTML, className: "prose-sm space-y-2" },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
