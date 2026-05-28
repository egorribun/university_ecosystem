import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { MessageInput } from "./MessageInput"

// Wave 194 SW3 — MessageInput Storybook fixture.
//
// Chat composer with a single `onSend(text, files)` prop and zero external
// context — fully standalone (no messenger/auth context). Blob URL previews,
// two-layer SVG rejection (W183 SW4), and FormData rely on browser APIs that
// work natively in the Storybook iframe. selectedFiles + text + the attach menu
// are internal state driven by user interaction (file input / typing), so
// static stories render the empty composer; the attachment-preview + active
// violet send-gradient states surface only via live interaction in the canvas.
// The component uses framer-motion `m.*` (+ AnimatePresence) → decorator adds
// LazyMotion (W124 SW1 mirror); `.messenger-theme` scopes the `--messenger-*`
// send-button tokens (W181 SW1).
//
// Variants: Default (desktop width), Mobile (narrow), DarkMode.

const themed = (dark: boolean, width = 420): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div
          className="messenger-theme flex flex-col justify-end bg-msg-chat"
          style={{ width, height: 200, overflow: "visible", padding: "1rem" }}
        >
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof MessageInput> = {
  title: "Messenger/MessageInput",
  component: MessageInput,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MessageInput>

export const Default: Story = {
  args: { onSend: () => {} },
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story:
          "Empty composer (send button disabled until text/files present). Attachment previews + the active violet send-gradient surface via live interaction.",
      },
    },
  },
}

export const Mobile: Story = {
  args: { onSend: () => {} },
  decorators: [themed(false, 340)],
  parameters: {
    docs: {
      description: {
        story: "Narrow (340px) container — exercises the responsive composer padding.",
      },
    },
  },
}

export const DarkMode: Story = {
  args: { onSend: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
