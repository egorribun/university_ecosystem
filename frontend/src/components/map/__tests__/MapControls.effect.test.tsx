import type { DependencyList, EffectCallback, MutableRefObject } from "react"
import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { MapRef } from "react-map-gl/maplibre"

const { effectCalls } = vi.hoisted(() => ({
  effectCalls: [] as Array<{ effect: EffectCallback; dependencies?: DependencyList }>,
}))

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react")
  return {
    ...actual,
    useEffect: (effect: EffectCallback, dependencies?: DependencyList) => {
      effectCalls.push({ effect, dependencies })
      return actual.useEffect(effect, dependencies)
    },
  }
})
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))

import { MapControls } from "@/components/map/MapControls"

describe("MapControls fullscreen effect contract", () => {
  it("keeps the fullscreen listener on a mount-only dependency tuple", () => {
    const ref = { current: null } as MutableRefObject<MapRef | null>
    render(<MapControls mapRef={ref} />)

    const fullscreenEffect = effectCalls.find(({ effect }) =>
      effect.toString().includes("fullscreenchange")
    )
    expect(fullscreenEffect?.dependencies).toEqual([])
  })
})
