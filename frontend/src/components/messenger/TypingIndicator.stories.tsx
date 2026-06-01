import type { Meta, StoryObj } from "@storybook/react-vite"
import { TypingIndicator } from "./TypingIndicator"

// Wave 192 SW2 — TypingIndicator Storybook fixture.
//
// Pattern source: `frontend/src/components/layout/Footer.stories.tsx` (W176
// SW5 canonical template). Global preview decorator (`.storybook/preview.tsx`)
// supplies I18nextProvider + LanguageProvider for the `useTranslation` hook
// inside TypingIndicator (W181 SW4 component). Wrapper decorator below
// provides a chat-area-like container so the typing chip renders against
// the appropriate `bg-msg-chat` surface with sufficient horizontal width.
//
// Variants:
//   • Empty — `users: []` returns null (no DOM emitted). Demonstrates the
//     guard at TypingIndicator.tsx:47.
//   • SingleUser — `users: [{userId, userName: "Alice"}]` renders
//     "Alice is typing..." (via `messenger:typing` i18n key with name
//     interpolation).
//   • MultipleUsers — `users: 3 entries` renders "3 people are typing..."
//     (via `messenger:typingMultiple` i18n key with count interpolation).
//   • ReducedMotion — `prefersReducedMotion: true` swaps the animated
//     3-dot pulse for static text ("Typing" via `messenger:isTyping` key).
//     Demonstrates the W181 SW4 reduced-motion swap pattern (defense-in-
//     depth alongside `@media (prefers-reduced-motion)` in
//     `tokens/messenger.css`).
//
// a11y notes: TypingIndicator uses `role="status"` + `aria-live="polite"`
// + sr-only label backup (W181 SW4 design). Storybook a11y addon should
// confirm 0 critical/serious violations across all variants.

const meta: Meta<typeof TypingIndicator> = {
  title: "Messenger/TypingIndicator",
  component: TypingIndicator,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <div className="flex min-h-[120px] w-full max-w-[800px] items-end bg-msg-chat p-4">
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof TypingIndicator>

export const Empty: Story = {
  args: {
    users: [],
    prefersReducedMotion: false,
  },
  parameters: {
    docs: {
      description: {
        story:
          "When `users` is empty, TypingIndicator returns null and emits no DOM. Useful for verifying the guard at TypingIndicator.tsx:47 against accidental empty-state rendering.",
      },
    },
  },
}

export const SingleUser: Story = {
  args: {
    users: [{ userId: "u1", userName: "Alice" }],
    prefersReducedMotion: false,
  },
}

export const MultipleUsers: Story = {
  args: {
    users: [
      { userId: "u1", userName: "Alice" },
      { userId: "u2", userName: "Bob" },
      { userId: "u3", userName: "Charlie" },
    ],
    prefersReducedMotion: false,
  },
}

export const ReducedMotion: Story = {
  args: {
    users: [{ userId: "u1", userName: "Alice" }],
    prefersReducedMotion: true,
  },
  parameters: {
    docs: {
      description: {
        story:
          "Under `prefersReducedMotion=true`, animated 3-dot pulse is replaced with static text per `messenger:isTyping` i18n key. Defense-in-depth alongside CSS `@media (prefers-reduced-motion)` block in `tokens/messenger.css`.",
      },
    },
  },
}

export const DarkMode: Story = {
  args: {
    users: [{ userId: "u1", userName: "Alice" }],
    prefersReducedMotion: false,
  },
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [
    (Story) => (
      <div className="dark">
        <Story />
      </div>
    ),
  ],
}
