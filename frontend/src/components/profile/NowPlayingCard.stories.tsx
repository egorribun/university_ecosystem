import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { NowPlaying } from "@/types/spotify"
import { NowPlayingCard } from "./NowPlayingCard"

// Wave 198 SW6 — NowPlayingCard Storybook fixture (profile, pure-props).
//
// Spotify "now playing" card driven entirely by the `data: NowPlaying` prop. The
// rAF progress loop only runs while is_playing + duration > 0; the album image
// loads from a CDN URL (fails → ♪ fallback, no rejection). Uses m.div → LazyMotion.
//
// Variants: Playing / Paused / DarkMode.

const PLAYING: NowPlaying = {
  is_playing: true,
  artists: ["M83"],
  track_id: "t1",
  track_name: "Midnight City",
  track_url: "https://open.spotify.com/track/t1",
  album_name: "Hurry Up, We're Dreaming",
  album_image_url: "https://picsum.photos/seed/album/200/200",
  progress_ms: 78_000,
  duration_ms: 244_000,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="profile-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 380 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof NowPlayingCard> = {
  title: "Profile/NowPlayingCard",
  component: NowPlayingCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { data: PLAYING },
}

export default meta
type Story = StoryObj<typeof NowPlayingCard>

export const Playing: Story = {
  decorators: [themed(false)],
}

export const Paused: Story = {
  args: { data: { ...PLAYING, is_playing: false } },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
