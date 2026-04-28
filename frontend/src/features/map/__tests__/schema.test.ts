import { describe, expect, it } from "vitest"
import * as v from "valibot"

import {
  mapSearchSchema,
  parseMapViewport,
  serializeMapViewport,
  type MapSearch,
  type MapViewport,
} from "../schema"

/**
 * Wave 120 SW5 Map URL-sync — schema + helpers contract tests.
 *
 * Verifies:
 *   - mapSearchSchema accepts both number and numeric-string inputs
 *     (TanStack Router parses URL params as either depending on context)
 *   - Out-of-range / NaN / non-string-non-number inputs fall back to
 *     undefined silently (don't throw — important so a bad URL doesn't
 *     crash the route, it just falls back to cinematic intro)
 *   - parseMapViewport returns null for incomplete (any field missing)
 *   - parseMapViewport normalizes bearing to [0, 360)
 *   - serializeMapViewport rounds to documented precision (5 dec lat/lng,
 *     1 dec zoom, 0 dec pitch + bearing) and returns NUMBERS not strings
 *     (clean URLs ?z=16 vs JSON-quoted ?z=%2216%22 — see SW5 commit body)
 *   - Round-trip serialize → parse preserves viewport within precision
 */

describe("mapSearchSchema", () => {
  it("accepts numeric inputs in valid range", () => {
    const result = v.parse(mapSearchSchema, {
      z: 16,
      lat: 55.7138,
      lng: 37.8159,
      p: 45,
      b: 90,
    })
    expect(result).toEqual({ z: 16, lat: 55.7138, lng: 37.8159, p: 45, b: 90 })
  })

  it("accepts numeric-string inputs (TanStack URL parser may pass strings)", () => {
    const result = v.parse(mapSearchSchema, {
      z: "16.5",
      lat: "55.71440",
      lng: "37.81600",
      p: "30",
      b: "0",
    })
    expect(result).toEqual({ z: 16.5, lat: 55.7144, lng: 37.816, p: 30, b: 0 })
  })

  it("falls back to undefined for non-numeric strings (e.g. ?z=abc)", () => {
    const result = v.parse(mapSearchSchema, {
      z: "abc",
      lat: 55.7138,
      lng: 37.8159,
      p: 45,
      b: 90,
    })
    expect(result.z).toBeUndefined()
    // Other valid fields preserved
    expect(result.lat).toBe(55.7138)
  })

  it("falls back to undefined for out-of-range values", () => {
    const result = v.parse(mapSearchSchema, {
      z: 25, // above max 20
      lat: 60, // above max 55.8
      lng: 50, // above max 37.9
      p: 90, // above max 70
      b: 90,
    })
    expect(result.z).toBeUndefined()
    expect(result.lat).toBeUndefined()
    expect(result.lng).toBeUndefined()
    expect(result.p).toBeUndefined()
    expect(result.b).toBe(90)
  })

  it("falls back to undefined for NaN-producing string transforms", () => {
    const result = v.parse(mapSearchSchema, {
      z: "Infinity",
      lat: "NaN",
      lng: 37.8159,
      p: 45,
      b: 90,
    })
    expect(result.z).toBeUndefined()
    expect(result.lat).toBeUndefined()
  })

  it("accepts empty object (all params optional)", () => {
    const result = v.parse(mapSearchSchema, {})
    expect(result).toEqual({})
  })

  it("ignores unknown fields", () => {
    const result = v.parse(mapSearchSchema, { z: 16, foo: "bar" })
    expect(result.z).toBe(16)
    expect((result as Record<string, unknown>).foo).toBeUndefined()
  })
})

describe("parseMapViewport", () => {
  it("returns null when any field is missing", () => {
    const partial: MapSearch = { z: 16, lat: 55.7138, lng: 37.8159, p: 45 } // no b
    expect(parseMapViewport(partial)).toBeNull()
  })

  it("returns null for fully empty input", () => {
    expect(parseMapViewport({})).toBeNull()
  })

  it("returns full viewport when all fields present", () => {
    const result = parseMapViewport({ z: 16, lat: 55.7138, lng: 37.8159, p: 45, b: 90 })
    expect(result).toEqual({
      zoom: 16,
      latitude: 55.7138,
      longitude: 37.8159,
      pitch: 45,
      bearing: 90,
    })
  })

  it("normalizes bearing to [0, 360) range", () => {
    expect(parseMapViewport({ z: 16, lat: 55.7138, lng: 37.8159, p: 45, b: 0 })?.bearing).toBe(0)
    expect(parseMapViewport({ z: 16, lat: 55.7138, lng: 37.8159, p: 45, b: 359 })?.bearing).toBe(
      359
    )
    // Bearing > 360 normalized via modulo at parse time. Schema range
    // accepts 0-360 inclusive; 360 normalizes to 0.
    expect(parseMapViewport({ z: 16, lat: 55.7138, lng: 37.8159, p: 45, b: 360 })?.bearing).toBe(0)
  })
})

describe("serializeMapViewport", () => {
  it("returns NUMBERS not strings (clean TanStack URLs)", () => {
    const state: MapViewport = {
      zoom: 16.5,
      latitude: 55.7144,
      longitude: 37.816,
      pitch: 30,
      bearing: 90,
    }
    const result = serializeMapViewport(state)
    expect(typeof result.z).toBe("number")
    expect(typeof result.lat).toBe("number")
    expect(typeof result.lng).toBe("number")
    expect(typeof result.p).toBe("number")
    expect(typeof result.b).toBe("number")
  })

  it("rounds zoom to 1 decimal", () => {
    const result = serializeMapViewport({
      zoom: 16.5678,
      latitude: 55.7138,
      longitude: 37.8159,
      pitch: 0,
      bearing: 0,
    })
    expect(result.z).toBe(16.6)
  })

  it("rounds lat/lng to 5 decimals (~1m accuracy at 55°N)", () => {
    const result = serializeMapViewport({
      zoom: 16,
      latitude: 55.71384567,
      longitude: 37.81591234,
      pitch: 0,
      bearing: 0,
    })
    expect(result.lat).toBe(55.71385)
    expect(result.lng).toBe(37.81591)
  })

  it("rounds pitch + bearing to integers", () => {
    const result = serializeMapViewport({
      zoom: 16,
      latitude: 55.7138,
      longitude: 37.8159,
      pitch: 30.7,
      bearing: 89.3,
    })
    expect(result.p).toBe(31)
    expect(result.b).toBe(89)
  })

  it("normalizes bearing to [0, 360) on serialize", () => {
    expect(
      serializeMapViewport({
        zoom: 16,
        latitude: 55.7138,
        longitude: 37.8159,
        pitch: 0,
        bearing: 360,
      }).b
    ).toBe(0)
    expect(
      serializeMapViewport({
        zoom: 16,
        latitude: 55.7138,
        longitude: 37.8159,
        pitch: 0,
        bearing: -10,
      }).b
    ).toBe(350)
    expect(
      serializeMapViewport({
        zoom: 16,
        latitude: 55.7138,
        longitude: 37.8159,
        pitch: 0,
        bearing: 720,
      }).b
    ).toBe(0)
  })
})

describe("round-trip serialize → parse", () => {
  it("preserves viewport within documented precision", () => {
    const initial: MapViewport = {
      zoom: 16.5,
      latitude: 55.7144,
      longitude: 37.816,
      pitch: 30,
      bearing: 90,
    }
    const serialized = serializeMapViewport(initial)
    const reparsed = v.parse(mapSearchSchema, serialized)
    const restored = parseMapViewport(reparsed)
    expect(restored).toEqual(initial)
  })

  it("preserves viewport with high-precision input within rounding budget", () => {
    const initial: MapViewport = {
      zoom: 16.567, // will round to 16.6
      latitude: 55.71384567, // will round to 55.71385
      longitude: 37.81591234, // will round to 37.81591
      pitch: 30.7, // will round to 31
      bearing: 89.3, // will round to 89
    }
    const serialized = serializeMapViewport(initial)
    const reparsed = v.parse(mapSearchSchema, serialized)
    const restored = parseMapViewport(reparsed)
    expect(restored).toEqual({
      zoom: 16.6,
      latitude: 55.71385,
      longitude: 37.81591,
      pitch: 31,
      bearing: 89,
    })
  })
})
