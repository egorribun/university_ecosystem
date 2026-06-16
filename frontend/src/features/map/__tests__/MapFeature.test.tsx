import { render, screen } from "@testing-library/react"
import type { ComponentType } from "react"
import { Suspense } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", resolvedLanguage: "en", changeLanguage: () => Promise.resolve() },
  }),
  // WidgetErrorBoundary's barrel transitively imports ErrorBoundary,
  // which wraps with withTranslation() at module-eval time.
  withTranslation: () => (Component: ComponentType) => Component,
  Trans: ({ children }: { children?: React.ReactNode }) => children,
}))

const mq = vi.hoisted(() => ({ value: false }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => mq.value }))

/* Sidestep the entire maplibre stack — the lazy child is replaced with null. */
vi.mock("@/components/map/MapLibreMap", () => ({ default: () => null }))

/* Module-mock every data/router hook MapFeature reaches. */
vi.mock("@/hooks/useURLState", () => ({
  useURLState: () => ({ params: {}, setParam: vi.fn(), setParams: vi.fn() }),
}))
vi.mock("@/hooks/useTimeOfDay", () => ({ useTimeOfDay: () => "afternoon" }))
vi.mock("@/hooks/useSeason", () => ({ useSeason: () => "spring" }))
vi.mock("@/hooks/useNextLesson", () => ({ useNextLesson: () => null }))
vi.mock("@/hooks/useScheduleData", () => ({ useScheduleData: () => ({ todayLessons: [] }) }))
vi.mock("@/hooks/useMapEvents", () => ({ useMapEvents: () => ({ events: [], isLoading: false }) }))
vi.mock("@/hooks/useMapWeather", () => ({
  useMapWeather: () => ({ data: undefined, isLoading: false }),
}))
vi.mock("@/hooks/useMapKeyboardShortcuts", () => ({ useMapKeyboardShortcuts: () => undefined }))

import { MapFeature } from "@/features/map/MapFeature"

function renderFeature() {
  return render(
    <Suspense fallback={null}>
      <MapFeature />
    </Suspense>
  )
}

describe("MapFeature", () => {
  afterEach(() => {
    mq.value = false
  })

  it("renders the feature shell with header, search bar, and category filter (wide)", () => {
    const { container } = renderFeature()
    // Page title + badge from MapHeader
    expect(screen.getByRole("heading", { name: /page\.title/ })).toBeInTheDocument()
    // Search combobox from MapSearchBar
    expect(screen.getByRole("combobox", { name: "search.ariaLabel" })).toBeInTheDocument()
    // Category radiogroup from MapCategoryFilter
    expect(screen.getByRole("radiogroup", { name: "categories.filterLabel" })).toBeInTheDocument()
    // Themed root with data attributes from useTimeOfDay / useSeason
    const root = container.querySelector(".map-theme")
    expect(root).not.toBeNull()
    expect(root).toHaveAttribute("data-time-period", "afternoon")
    expect(root).toHaveAttribute("data-season", "spring")
  })

  it("does not render the building sidebar when no building is selected", () => {
    renderFeature()
    // Sidebar only mounts when currentBuilding is truthy (none selected on mount)
    expect(screen.queryByText("sidebar.close")).not.toBeInTheDocument()
  })

  it("renders the all-categories filter with the 'all' radio active by default", () => {
    renderFeature()
    const radios = screen.getAllByRole("radio")
    expect(radios.length).toBeGreaterThan(0)
    const allRadio = radios[0]!
    expect(allRadio).toHaveAttribute("aria-checked", "true")
  })

  it("renders the narrow-viewport branch (useMediaQuery true)", () => {
    mq.value = true
    const { container } = renderFeature()
    expect(screen.getByRole("heading", { name: /page\.title/ })).toBeInTheDocument()
    expect(container.querySelector(".map-theme")).not.toBeNull()
  })
})
