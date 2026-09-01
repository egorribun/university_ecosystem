import { act, cleanup, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  reducedMotion: false,
  lowPower: false,
  useMediaQuery: vi.fn(),
  isLowPowerDevice: vi.fn(),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: state.useMediaQuery,
}))

vi.mock("@/utils/deviceCapabilities", () => ({
  isLowPowerDevice: state.isLowPowerDevice,
}))

import { WeatherParticles } from "@/components/map/WeatherParticles"

const frameCallbacks: FrameRequestCallback[] = []
const resizeObservers: ResizeObserverStub[] = []
let nextFrameId = 0
let fillStyleValue = ""
let strokeStyleValue = ""
let globalAlphaValue = 1
const fillStyleValues: string[] = []
const strokeStyleValues: string[] = []
const globalAlphaValues: number[] = []

const canvasContext = {
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  get fillStyle() {
    return fillStyleValue
  },
  set fillStyle(value: string) {
    fillStyleValue = value
    fillStyleValues.push(value)
  },
  get strokeStyle() {
    return strokeStyleValue
  },
  set strokeStyle(value: string) {
    strokeStyleValue = value
    strokeStyleValues.push(value)
  },
  lineWidth: 1,
  get globalAlpha() {
    return globalAlphaValue
  },
  set globalAlpha(value: number) {
    globalAlphaValue = value
    globalAlphaValues.push(value)
  },
} as unknown as CanvasRenderingContext2D

class ResizeObserverStub {
  readonly callback: ResizeObserverCallback
  readonly observe = vi.fn()
  readonly disconnect = vi.fn()

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
    resizeObservers.push(this)
  }

  trigger() {
    this.callback([], this as unknown as ResizeObserver)
  }
}

function setDimensions(width: number, height: number) {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => width,
  })
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get: () => height,
  })
}

function runFrame(now: number) {
  const callback = frameCallbacks.shift()
  expect(callback).toBeDefined()
  act(() => callback?.(now))
}

function renderCondition(condition: "rain" | "snow" | "storm" | "fog", isDark = false) {
  return render(<WeatherParticles condition={condition} isDark={isDark} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  frameCallbacks.length = 0
  resizeObservers.length = 0
  nextFrameId = 0
  fillStyleValue = ""
  strokeStyleValue = ""
  globalAlphaValue = 1
  fillStyleValues.length = 0
  strokeStyleValues.length = 0
  globalAlphaValues.length = 0
  state.reducedMotion = false
  state.lowPower = false
  state.useMediaQuery.mockImplementation(() => state.reducedMotion)
  state.isLowPowerDevice.mockImplementation(() => state.lowPower)
  setDimensions(100, 80)
  vi.stubGlobal("ResizeObserver", ResizeObserverStub)
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(canvasContext)
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
    frameCallbacks.push(callback)
    nextFrameId += 1
    return nextFrameId
  })
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined)
  vi.spyOn(performance, "now").mockReturnValue(0)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("WeatherParticles mutation contracts", () => {
  it("does not mount effects for non-drawing conditions or blocked devices", () => {
    for (const props of [
      { condition: "clear" as const, reducedMotion: false, lowPower: false },
      { condition: "cloudy" as const, reducedMotion: false, lowPower: false },
      { condition: "unknown" as never, reducedMotion: false, lowPower: false },
      { condition: "rain" as const, reducedMotion: true, lowPower: false },
      { condition: "rain" as const, reducedMotion: false, lowPower: true },
    ]) {
      state.reducedMotion = props.reducedMotion
      state.lowPower = props.lowPower
      const view = render(<WeatherParticles condition={props.condition} isDark={false} />)
      expect(view.container.querySelector("canvas")).toBeNull()
      expect(window.requestAnimationFrame).not.toHaveBeenCalled()
      cleanup()
      frameCallbacks.length = 0
      vi.mocked(window.requestAnimationFrame).mockClear()
    }

    expect(state.useMediaQuery).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    expect(state.isLowPowerDevice).toHaveBeenCalled()
  })

  it.each([
    ["rain", 200, "line", "#60a5fa", "#93c5fd", 3, 9, 0.5],
    ["snow", 100, "arc", "#f8fafc", "#e2e8f0", 2, 1, 0.6],
    ["storm", 250, "line", "#60a5fa", "#93c5fd", 3, 12, 0.55],
    ["fog", 50, "arc", "#cbd5e1", "#94a3b8", 15, 0.4, 0.08],
  ] as const)(
    "initializes the %s configuration with exact count, midpoint ranges, and colors",
    (condition, count, shape, lightColor, darkColor, size, speed, opacity) => {
      vi.spyOn(Math, "random").mockReturnValue(0.5)
      const light = renderCondition(condition)
      runFrame(16)

      expect(light.container.querySelector("canvas")).toHaveProperty("width", 100)
      expect(light.container.querySelector("canvas")).toHaveProperty("height", 80)
      expect(light.container.querySelector("[aria-hidden='true']")).toHaveStyle({ zIndex: "1" })
      expect(
        light.container.querySelector(".absolute.inset-0.pointer-events-none")
      ).toBeInTheDocument()
      if (shape === "line") {
        expect(canvasContext.moveTo).toHaveBeenCalledTimes(count)
        expect(canvasContext.lineTo).toHaveBeenCalledTimes(count)
        expect(canvasContext.stroke).toHaveBeenCalledTimes(count)
        expect(strokeStyleValues).toContain(lightColor)
      } else {
        expect(canvasContext.arc).toHaveBeenCalledTimes(count)
        expect(canvasContext.fill).toHaveBeenCalledTimes(count)
        expect(fillStyleValues).toContain(lightColor)
      }
      expect(globalAlphaValues.some((value) => Math.abs(value - opacity) < 1e-9)).toBe(true)
      light.unmount()
      frameCallbacks.length = 0
      vi.clearAllMocks()

      const dark = renderCondition(condition, true)
      runFrame(16)
      if (shape === "line") {
        expect(strokeStyleValues).toContain(darkColor)
      } else {
        expect(fillStyleValues).toContain(darkColor)
      }
      expect(canvasContext.clearRect).toHaveBeenCalledWith(0, 0, 100, 80)
      expect(size).toBeGreaterThan(0)
      expect(speed).toBeGreaterThan(0)
      dark.unmount()
    }
  )

  it("uses lower range bounds, preserves drift signs, and draws exact particle geometry", () => {
    vi.spyOn(Math, "random").mockReturnValue(0)

    const rain = renderCondition("rain")
    runFrame(16)
    expect(vi.mocked(canvasContext.moveTo).mock.calls[0]![0]).toBeCloseTo(-0.5 * (16 / 16.667), 5)
    expect(vi.mocked(canvasContext.moveTo).mock.calls[0]![1]).toBeCloseTo(6 * (16 / 16.667), 5)
    expect(vi.mocked(canvasContext.lineTo).mock.calls[0]![0]).toBeCloseTo(
      vi.mocked(canvasContext.moveTo).mock.calls[0]![0]! - 0.5 * 0.5,
      5
    )
    expect(vi.mocked(canvasContext.lineTo).mock.calls[0]![1]).toBeCloseTo(
      vi.mocked(canvasContext.moveTo).mock.calls[0]![1]! + 2,
      5
    )
    expect(globalAlphaValues.some((value) => Math.abs(value - 0.3) < 1e-9)).toBe(true)
    rain.unmount()
    frameCallbacks.length = 0
    vi.clearAllMocks()

    const snow = renderCondition("snow")
    runFrame(16)
    const snowArc = vi.mocked(canvasContext.arc).mock.calls[0]!
    expect(snowArc[0]).toBeCloseTo(Math.sin(0.016) * 0.3 * (16 / 16.667) - 0.8 * (16 / 16.667), 5)
    expect(snowArc[1]).toBeCloseTo(0.5 * (16 / 16.667), 5)
    expect(snowArc[2]).toBe(1)
    expect(snowArc[3]).toBe(0)
    expect(snowArc[4]).toBeCloseTo(Math.PI * 2, 8)
    expect(globalAlphaValues.some((value) => Math.abs(value - 0.4) < 1e-9)).toBe(true)
    snow.unmount()
    frameCallbacks.length = 0
    vi.clearAllMocks()

    const fog = renderCondition("fog")
    runFrame(16)
    const fogArc = vi.mocked(canvasContext.arc).mock.calls[0]!
    fog.unmount()
    expect(fogArc[0]).toBeCloseTo(-0.4 * (16 / 16.667), 5)
    expect(fogArc[1]).toBeCloseTo(0.2 * (16 / 16.667), 5)
    expect(fogArc[2]).toBe(10)
    expect(fogArc[3]).toBe(0)
    expect(fogArc[4]).toBeCloseTo(Math.PI * 2, 8)
    expect(globalAlphaValues.some((value) => Math.abs(value - 0.04) < 1e-9)).toBe(true)
  })

  it("caps frame deltas, applies normalized motion, and keeps snow drift distinct", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.75)
    const rain = renderCondition("rain")
    runFrame(16)
    const firstY = vi.mocked(canvasContext.moveTo).mock.calls[0]![1] as number
    expect(firstY).toBeCloseTo(60 + 10.5 * (16 / 16.667), 5)
    runFrame(32)
    const secondY = vi.mocked(canvasContext.moveTo).mock.calls[200]![1] as number
    expect(secondY).toBeCloseTo(60 + 10.5 * (16 / 16.667) * 2, 5)
    const firstMove = vi.mocked(canvasContext.moveTo).mock.calls[0]!
    const firstLine = vi.mocked(canvasContext.lineTo).mock.calls[0]!
    expect(firstLine[0]).toBeCloseTo((firstMove[0] as number) + 0.25 * 0.5, 5)
    expect(firstLine[1]).toBeCloseTo((firstMove[1] as number) + 3.5, 5)
    rain.unmount()
    frameCallbacks.length = 0
    vi.clearAllMocks()

    const snow = renderCondition("snow")
    runFrame(16)
    const snowArc = vi.mocked(canvasContext.arc).mock.calls[0]!
    expect(snowArc[0]).toBeCloseTo(
      75 + Math.sin(0.016) * 0.3 * (16 / 16.667) + 0.4 * (16 / 16.667),
      5
    )
    expect(snowArc[1]).toBeCloseTo(60 + 1.25 * (16 / 16.667), 5)
    snow.unmount()
  })

  it("recycles vertical particles with negative spawn positions and fog particles on both sides", () => {
    setDimensions(10, 10)
    vi.spyOn(Math, "random").mockReturnValue(0.999)
    const rain = renderCondition("rain")
    runFrame(16)
    expect(vi.mocked(canvasContext.moveTo).mock.calls[0]![0]).toBeCloseTo(9.99, 2)
    expect(vi.mocked(canvasContext.moveTo).mock.calls[0]![1] as number).toBeLessThan(0)
    rain.unmount()
    frameCallbacks.length = 0
    vi.clearAllMocks()

    vi.mocked(Math.random).mockReturnValue(0)
    const fogRight = renderCondition("fog")
    for (let index = 0; index < 32; index += 1) {
      runFrame((index + 1) * 50)
    }
    expect(vi.mocked(canvasContext.arc).mock.calls.some(([x]) => (x as number) > 10)).toBe(true)
    fogRight.unmount()
    frameCallbacks.length = 0
    vi.clearAllMocks()

    vi.mocked(Math.random).mockReturnValue(0.999)
    const fogLeft = renderCondition("fog")
    for (let index = 0; index < 24; index += 1) {
      runFrame((index + 1) * 50)
    }
    expect(vi.mocked(canvasContext.arc).mock.calls.some(([x]) => (x as number) < 0)).toBe(true)
    fogLeft.unmount()
  })

  it("schedules and fades a storm flash at the configured interval", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    const storm = renderCondition("storm")
    for (let index = 0; index <= 100; index += 1) {
      runFrame(index === 0 ? 50 : 50 + index * 50)
    }
    expect(canvasContext.fillRect).not.toHaveBeenCalled()

    for (let index = 101; index <= 110; index += 1) {
      runFrame(50 + index * 50)
    }
    expect(canvasContext.fillRect).toHaveBeenCalled()
    expect(vi.mocked(canvasContext.fillRect).mock.calls[0]).toEqual([0, 0, 100, 80])
    expect(fillStyleValues).toContain("rgba(255, 255, 255, 0.08)")

    runFrame(50 + 111 * 50)
    runFrame(50 + 112 * 50)
    expect(vi.mocked(canvasContext.fillRect).mock.calls).toHaveLength(2)
    storm.unmount()
  })

  it("pauses hidden documents, resumes on visibility, and cleans every resource", () => {
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false)
    const addDocument = vi.spyOn(document, "addEventListener")
    const removeDocument = vi.spyOn(document, "removeEventListener")
    const rain = renderCondition("rain")
    expect(addDocument).toHaveBeenCalledWith("visibilitychange", expect.any(Function))
    runFrame(16)

    hidden.mockReturnValue(true)
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(window.cancelAnimationFrame).toHaveBeenCalled()
    const clearCount = vi.mocked(canvasContext.clearRect).mock.calls.length
    runFrame(1000)
    expect(vi.mocked(canvasContext.clearRect).mock.calls.length).toBe(clearCount)

    hidden.mockReturnValue(false)
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(window.requestAnimationFrame).toHaveBeenCalledTimes(3)
    runFrame(1050)
    expect(vi.mocked(canvasContext.clearRect).mock.calls.length).toBeGreaterThan(clearCount)

    rain.unmount()
    expect(resizeObservers[0]?.disconnect).toHaveBeenCalled()
    expect(removeDocument).toHaveBeenCalledWith("visibilitychange", expect.any(Function))
  })

  it("reinitializes particles and dimensions after a ResizeObserver callback", () => {
    const rain = renderCondition("rain")
    const canvas = rain.container.querySelector("canvas")!
    expect(canvas).toHaveProperty("width", 100)
    expect(canvas).toHaveProperty("height", 80)

    setDimensions(320, 180)
    resizeObservers[0]?.trigger()
    expect(canvas).toHaveProperty("width", 320)
    expect(canvas).toHaveProperty("height", 180)
    expect(resizeObservers[0]?.observe).toHaveBeenCalledWith(rain.container.querySelector("div"))
  })

  it("keeps the canvas shell when the context is unavailable and tears down on prop changes", () => {
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValueOnce(null)
    const noContext = renderCondition("rain")
    expect(noContext.container.querySelector("canvas")).toBeInTheDocument()
    expect(window.requestAnimationFrame).not.toHaveBeenCalled()
    noContext.unmount()

    frameCallbacks.length = 0
    vi.clearAllMocks()
    const view = renderCondition("rain")
    runFrame(16)
    view.rerender(<WeatherParticles condition="snow" isDark={false} />)
    expect(window.cancelAnimationFrame).toHaveBeenCalled()
    expect(view.container.querySelector("canvas")).toBeInTheDocument()
    view.rerender(<WeatherParticles condition="clear" isDark={false} />)
    expect(view.container.querySelector("canvas")).toBeNull()
  })
})
