import { useRef } from "react"
import type { MarkerInstance } from "react-map-gl/maplibre"
import { describe, expect, it } from "vitest"
import { render } from "@testing-library/react"
import {
  stripMaplibreMarkerChrome,
  useStripMaplibreMarkerChrome,
} from "../stripMaplibreMarkerChrome"

function markerFor(element: HTMLElement): MarkerInstance {
  return { getElement: () => element } as unknown as MarkerInstance
}

const markerWithoutElement = { getElement: () => null } as unknown as MarkerInstance

function HookProbe({ marker }: { marker: MarkerInstance | null }) {
  const ref = useRef<MarkerInstance | null>(marker)
  useStripMaplibreMarkerChrome(ref)
  return null
}

describe("stripMaplibreMarkerChrome", () => {
  it("removes MapLibre's duplicate interactive semantics from the marker wrapper", () => {
    const element = document.createElement("div")
    element.setAttribute("role", "button")
    element.setAttribute("aria-label", "Map marker")
    element.setAttribute("tabindex", "0")

    stripMaplibreMarkerChrome(markerFor(element))

    expect(element).not.toHaveAttribute("role")
    expect(element).not.toHaveAttribute("aria-label")
    expect(element).not.toHaveAttribute("tabindex")
  })

  it("is safe for missing marker elements and applies the same rule through the hook", () => {
    expect(() => stripMaplibreMarkerChrome(null)).not.toThrow()
    expect(() => stripMaplibreMarkerChrome(markerWithoutElement)).not.toThrow()

    const element = document.createElement("div")
    element.setAttribute("role", "button")
    render(<HookProbe marker={markerFor(element)} />)

    expect(element).not.toHaveAttribute("role")
  })

  it("is safe when a hook marker has no mounted element", () => {
    expect(() => render(<HookProbe marker={markerWithoutElement} />)).not.toThrow()
  })

  it("is safe when the hook ref has no marker", () => {
    expect(() => render(<HookProbe marker={null} />)).not.toThrow()
  })
})
