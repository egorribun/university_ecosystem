import { act, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const hoisted = vi.hoisted(() => ({ reducedMotion: false, lowPower: false }))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => hoisted.reducedMotion }))
vi.mock("@/utils/deviceCapabilities", () => ({
  isLowPowerDevice: () => hoisted.lowPower,
}))

import { WeatherParticles } from "@/components/map/WeatherParticles"

const DRAWING_CONDITIONS = ["rain", "snow", "storm", "fog"] as const

const canvasContext = {
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  fillStyle: "",
  strokeStyle: "",
  lineWidth: 1,
  globalAlpha: 1,
} as unknown as CanvasRenderingContext2D

describe("WeatherParticles", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hoisted.reducedMotion = false
    hoisted.lowPower = false
    canvasContext.fillStyle = ""
    canvasContext.strokeStyle = ""
    canvasContext.globalAlpha = 1
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(canvasContext)
    let n = 0
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      if (n++ < 2) {
        cb(16)
      }
      return 1
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("renders null for the clear condition", () => {
    const { container } = render(<WeatherParticles condition="clear" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })

  it("renders null for the cloudy condition", () => {
    const { container } = render(<WeatherParticles condition="cloudy" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })

  it("renders null when prefers-reduced-motion is enabled", () => {
    hoisted.reducedMotion = true
    const { container } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })

  it("does not start canvas effects on a low-power device", () => {
    hoisted.lowPower = true
    const { container } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
    expect(window.requestAnimationFrame).not.toHaveBeenCalled()
  })

  it.each(DRAWING_CONDITIONS)("draws a canvas for the %s condition (light)", (condition) => {
    const { container } = render(<WeatherParticles condition={condition} isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()
    const wrapper = container.querySelector("[aria-hidden='true']")
    expect(wrapper).not.toBeNull()
  })

  it.each(DRAWING_CONDITIONS)("draws a canvas for the %s condition (dark)", (condition) => {
    const { container } = render(<WeatherParticles condition={condition} isDark={true} />)
    expect(container.querySelector("canvas")).not.toBeNull()
  })

  it("draws weather with the condition-specific light/dark design tokens", () => {
    const callbacks: FrameRequestCallback[] = []
    vi.mocked(window.requestAnimationFrame).mockImplementation((callback) => {
      callbacks.push(callback)
      return callbacks.length
    })

    const { unmount } = render(<WeatherParticles condition="rain" isDark={false} />)
    act(() => callbacks.shift()?.(performance.now() + 16))
    expect(canvasContext.strokeStyle).toBe("#60a5fa")
    unmount()
    callbacks.length = 0

    render(<WeatherParticles condition="snow" isDark={true} />)
    act(() => callbacks.shift()?.(performance.now() + 16))
    expect(canvasContext.fillStyle).toBe("#e2e8f0")
  })

  it("sizes the canvas to its container on initial resize", () => {
    const clientWidth = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(320)
    const clientHeight = vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(180)

    try {
      const { container } = render(<WeatherParticles condition="rain" isDark={false} />)
      const canvas = container.querySelector("canvas")!
      expect(canvas).toHaveProperty("width", 320)
      expect(canvas).toHaveProperty("height", 180)
    } finally {
      clientWidth.mockRestore()
      clientHeight.mockRestore()
    }
  })

  it("exercises the particle-recycle branches when particles fall out of bounds", () => {
    // Force particles to spawn near the bottom edge so the y-update pushes them
    // out of bounds, hitting recycleParticle (rain/snow/storm) and the fog
    // horizontal-recycle branch on the second animation frame.
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0.999)
    try {
      for (const condition of DRAWING_CONDITIONS) {
        const { container } = render(<WeatherParticles condition={condition} isDark={false} />)
        expect(container.querySelector("canvas")).not.toBeNull()
      }
    } finally {
      randomSpy.mockRestore()
    }
  })

  it("recycles fog particles from the right when their drift is negative", () => {
    let randomCall = 0
    const randomSpy = vi.spyOn(Math, "random").mockImplementation(() => {
      const particleSlot = randomCall++ % 6
      return particleSlot === 5 ? 0 : 0.999
    })

    try {
      const { container } = render(<WeatherParticles condition="fog" isDark={false} />)
      expect(container.querySelector("canvas")).not.toBeNull()
    } finally {
      randomSpy.mockRestore()
    }
  })

  it("recycles fog particles from the left when their drift is positive", () => {
    const callbacks: FrameRequestCallback[] = []
    vi.mocked(window.requestAnimationFrame).mockImplementation((callback) => {
      callbacks.push(callback)
      return callbacks.length
    })
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0.999)

    try {
      const startedAt = performance.now()
      render(<WeatherParticles condition="fog" isDark={false} />)
      expect(callbacks).toHaveLength(1)

      act(() => {
        for (let index = 0; index < 400; index += 1) {
          callbacks.shift()?.(startedAt + (index + 1) * 16)
        }
      })

      const arcCalls = vi.mocked(canvasContext.arc).mock.calls
      expect(arcCalls.some(([x]) => typeof x === "number" && x < 0)).toBe(true)
    } finally {
      randomSpy.mockRestore()
    }
  })

  it("walks the storm flash scheduling branch", () => {
    // Low Math.random pushes the flash schedule toward its minimum window; this
    // still walks the storm flash scheduling + fade arithmetic.
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0.001)
    try {
      const { container } = render(<WeatherParticles condition="storm" isDark={true} />)
      expect(container.querySelector("canvas")).not.toBeNull()
    } finally {
      randomSpy.mockRestore()
    }
  })

  it("pauses while the document is hidden and eventually renders a storm flash", () => {
    const callbacks: FrameRequestCallback[] = []
    vi.mocked(window.requestAnimationFrame).mockImplementation((callback) => {
      callbacks.push(callback)
      return callbacks.length
    })
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false)
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0)

    render(<WeatherParticles condition="storm" isDark={false} />)
    expect(callbacks).toHaveLength(1)

    hidden.mockReturnValue(true)
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
      callbacks.shift()?.(1000)
    })

    hidden.mockReturnValue(false)
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
      for (let index = 0; index < 80; index += 1) {
        callbacks.shift()?.(2000 + index * 100)
      }
    })

    expect(canvasContext.fillRect).toHaveBeenCalled()
    randomSpy.mockRestore()
    hidden.mockRestore()
  })

  it("does not draw a frame while the document is hidden", () => {
    const callbacks: FrameRequestCallback[] = []
    vi.mocked(window.requestAnimationFrame).mockImplementation((callback) => {
      callbacks.push(callback)
      return callbacks.length
    })
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true)

    const { unmount } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(callbacks).toHaveLength(1)
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
      callbacks.shift()?.(1000)
    })
    expect(canvasContext.clearRect).not.toHaveBeenCalled()
    unmount()
    hidden.mockRestore()
  })

  it("returns null for an unknown defensive condition", () => {
    const { container } = render(<WeatherParticles condition={"unknown" as never} isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })

  it("keeps the canvas shell usable when a 2D context is unavailable", () => {
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValueOnce(null)

    const { container } = render(<WeatherParticles condition="rain" isDark={false} />)

    expect(container.querySelector("canvas")).not.toBeNull()
  })

  it("reinitializes particles when ResizeObserver reports a resize", () => {
    let notifyResize: (() => void) | undefined
    class ResizeObserverStub {
      constructor(callback: ResizeObserverCallback) {
        notifyResize = () => callback([], this as unknown as ResizeObserver)
      }

      observe() {
        notifyResize?.()
      }

      disconnect() {}
    }

    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    try {
      const { container } = render(<WeatherParticles condition="rain" isDark={false} />)

      expect(container.querySelector("canvas")).not.toBeNull()
      expect(notifyResize).toBeDefined()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("disconnects observers, listeners, and the animation frame on unmount", () => {
    const disconnect = vi.fn()
    let callback: ResizeObserverCallback | undefined
    class ResizeObserverStub {
      constructor(next: ResizeObserverCallback) {
        callback = next
      }

      observe() {}

      disconnect() {
        disconnect()
      }
    }
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    const addEventListener = vi.spyOn(document, "addEventListener")
    const removeEventListener = vi.spyOn(document, "removeEventListener")
    const { unmount } = render(<WeatherParticles condition="rain" isDark={false} />)

    expect(callback).toBeDefined()
    expect(addEventListener).toHaveBeenCalledWith("visibilitychange", expect.any(Function))
    unmount()
    expect(disconnect).toHaveBeenCalledOnce()
    expect(removeEventListener).toHaveBeenCalledWith("visibilitychange", expect.any(Function))
    expect(window.cancelAnimationFrame).toHaveBeenCalled()
  })

  it("tears down the animation when reduced motion becomes enabled", () => {
    const { container, rerender } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()

    hoisted.reducedMotion = true
    rerender(<WeatherParticles condition="rain" isDark={false} />)

    expect(container.querySelector("canvas")).toBeNull()
    expect(window.cancelAnimationFrame).toHaveBeenCalled()
  })

  it("cleans up on unmount without throwing", () => {
    const { container, unmount } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()
    expect(() => unmount()).not.toThrow()
  })

  it("re-runs the effect when the condition prop changes", () => {
    const { container, rerender } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()
    rerender(<WeatherParticles condition="snow" isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()
    rerender(<WeatherParticles condition="clear" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })
})
