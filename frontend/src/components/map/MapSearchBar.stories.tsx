import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { MapSearchBar } from "./MapSearchBar"
import type { CampusBuilding } from "@/data/campusBuildings"

// Wave 196 SW1 — MapSearchBar Storybook fixture (LEAF tier batch 2).
//
// Fuzzy autocomplete over buildings + rooms (role="combobox"). Renders from
// `buildings` + callbacks alone — the dropdown only appears once the user types,
// so the static story shows the empty combobox input. The `buildings` fixture is
// a minimal CampusBuilding[] (only the fields the component reads — name/letter/
// floorCount/floors[].rooms[]) cast `as unknown as CampusBuilding[]`. No
// framer-motion → no LazyMotion. `.map-theme` supplies `.map-card-matte` tokens.
//
// Variants: Default / DarkMode.

const buildings = [
  {
    letter: "ГУК",
    name: "Main Academic Building",
    floorCount: 8,
    floors: [
      {
        floor: 3,
        rooms: [
          { id: "ГУК-305", name: "Lecture Hall 305" },
          { id: "ГУК-310", name: "Seminar Room 310" },
        ],
      },
    ],
  },
  {
    letter: "ЛК",
    name: "Lecture Complex",
    floorCount: 6,
    floors: [{ floor: 2, rooms: [{ id: "ЛК-201", name: "Auditorium 201" }] }],
  },
] as unknown as CampusBuilding[]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="map-theme"
        style={{ background: "var(--bg-page)", padding: "2rem", width: 360 }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof MapSearchBar> = {
  title: "Map/MapSearchBar",
  component: MapSearchBar,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MapSearchBar>

export const Default: Story = {
  args: { buildings, onSelectBuilding: () => {}, onSelectRoom: () => {} },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { buildings, onSelectBuilding: () => {}, onSelectRoom: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
