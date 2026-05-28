import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { ActivityHeatmap } from "./ActivityHeatmap"

// Wave 194 SW1 — ActivityHeatmap Storybook fixture.
//
// CSS Grid 7×N calendar with 5-level emerald intensity via `--activity-heat-*`
// tokens. Props: `data: Map<string,number>` (YYYY-MM-DD → count), `period`
// ("30d"|"90d"|"180d"), required `ariaLabel`. Uses `useLanguage()` (satisfied
// by the global preview LanguageProvider) + renders inside CardShell. NO
// framer-motion → no LazyMotion needed; still wraps `.activity-theme` for the
// heat tokens.
//
// Determinism note: the component builds its date grid from `new Date()`, so
// data MUST be TODAY-relative to populate cells. The grid + month labels
// therefore shift by calendar day; counts are deterministic per relative-day
// offset (W184 SW2 jitter formula, no Math.random). Chromatic is collect-only
// (W112 SW1), so the daily grid drift auto-accepts as a new baseline rather
// than a CI diff. Uses `render` (not `args`) to pass the Map directly + avoid
// Storybook arg-processing of a Map.
//
// Variants: Default (90d dense), Sparse (30d, every 3rd day), DarkMode.

function buildHeatmapData(days: number, sparse = false): Map<string, number> {
  const map = new Map<string, number>()
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  for (let i = 0; i < days; i++) {
    if (sparse && i % 3 !== 0) continue
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
    map.set(key, (i * 7) % 13) // deterministic 0..12 spread
  }
  return map
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="activity-theme"
        style={{ background: "var(--bg-page)", padding: "1.5rem", maxWidth: 720 }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof ActivityHeatmap> = {
  title: "Features/Activity/ActivityHeatmap",
  component: ActivityHeatmap,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ActivityHeatmap>

export const Default: Story = {
  render: () => (
    <ActivityHeatmap
      data={buildHeatmapData(90)}
      period="90d"
      ariaLabel="Activity heatmap for the last 90 days"
    />
  ),
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story:
          "Dense 90-day heatmap. All 5 intensity levels appear via the deterministic count spread; cells carry per-day role=img + aria-label per A11Y-85-01.",
      },
    },
  },
}

export const Sparse: Story = {
  render: () => (
    <ActivityHeatmap
      data={buildHeatmapData(30, true)}
      period="30d"
      ariaLabel="Activity heatmap for the last 30 days"
    />
  ),
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story:
          "30-day window with only every 3rd day populated — exercises the level-0 empty cells.",
      },
    },
  },
}

export const DarkMode: Story = {
  render: () => (
    <ActivityHeatmap
      data={buildHeatmapData(90)}
      period="90d"
      ariaLabel="Activity heatmap for the last 90 days"
    />
  ),
  decorators: [themed(true)],
  parameters: {
    backgrounds: { default: "dark" },
  },
}
