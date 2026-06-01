import type { Meta, StoryObj } from "@storybook/react-vite"
import { MessengerBackdrop } from "./MessengerBackdrop"

// Wave 192 SW2 — MessengerBackdrop Storybook fixture.
//
// Pattern source: `frontend/src/components/layout/Footer.stories.tsx` (W176
// SW5 canonical template). Global preview decorator (`.storybook/preview.tsx`)
// supplies TanStack Router + I18nextProvider + LanguageProvider + AuthContext
// + global Tailwind CSS — MessengerBackdrop renders inside a `.relative`
// `bg-msg-chat` container per variant decorator below (the component uses
// `absolute inset-0` positioning per W181 SW2, so it needs a positioned
// parent to render correctly; messenger production page uses
// `MessengerFeature.tsx`'s top-level `relative` wrapper).
//
// Variants:
//   • Default — light theme, full prop defaults (isNarrow=false, isMobile=
//     false, prefersReducedMotion=false). Full blur orbs at maximum size.
//   • DarkMode — adds `dark` class via decorator wrapper + dark background.
//     Demonstrates `--messenger-orb-1/2/3` token override behavior across
//     light + dark theme contexts.
//   • Narrow — `isNarrow=true` + mobile1 viewport. Smaller orb dimensions
//     scale appropriately for sub-content-breakpoint (~<900px) viewports.
//   • ReducedMotion — `prefersReducedMotion=true` drops `filter: blur(...)`
//     on each orb to save mobile GPU. Demonstrates the W183 SW7 GPU-savings
//     pattern (same effect fires when `isMobile=true` — both gate via the
//     internal `dropBlur` derivation in MessengerBackdrop.tsx:51).

const meta: Meta<typeof MessengerBackdrop> = {
  title: "Messenger/MessengerBackdrop",
  component: MessengerBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <div className="relative h-[600px] w-full overflow-hidden bg-msg-chat">
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>Sample chat surface — orbs render behind this text</span>
        </div>
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof MessengerBackdrop>

export const Default: Story = {
  args: {
    isNarrow: false,
    isMobile: false,
    prefersReducedMotion: false,
  },
}

export const DarkMode: Story = {
  args: {
    isNarrow: false,
    isMobile: false,
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

export const Narrow: Story = {
  args: {
    isNarrow: true,
    isMobile: false,
    prefersReducedMotion: false,
  },
  parameters: {
    viewport: {
      defaultViewport: "mobile1",
    },
  },
}

export const ReducedMotion: Story = {
  args: {
    isNarrow: false,
    isMobile: false,
    prefersReducedMotion: true,
  },
}
