import { act, render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.documentElement.style.removeProperty("--primary-main")
  document.documentElement.style.removeProperty("--primary-hover")
})

describe("ParticleAuthBackground closure", () => {
  it("renders the lightweight layout fallback in E2E mode", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_E2E_MODE", "true")
    const { default: ParticleAuthBackground } = await import("../ParticleAuthBackground")
    const { container } = render(<ParticleAuthBackground />)

    expect(container.querySelector("canvas")).not.toBeInTheDocument()
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true")
    expect(container.firstElementChild?.querySelector(".bg-linear-to-b")).toBeInTheDocument()
  })

  it("stops safely when the canvas context is unavailable", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_E2E_MODE", "")
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null)
    const { default: ParticleAuthBackground } = await import("../ParticleAuthBackground")
    const { container } = render(<ParticleAuthBackground />)

    expect(container.querySelector("canvas")).toBeInTheDocument()
  })

  it("runs and cleans up the particle, pointer, resize, and theme lifecycles", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_E2E_MODE", "")
    vi.useFakeTimers()

    const context = {
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      fillStyle: "",
    }
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      context as unknown as CanvasRenderingContext2D
    )
    let randomCall = 0
    vi.spyOn(Math, "random").mockImplementation(() => {
      randomCall += 1
      const particleOffset = randomCall - 8
      if (particleOffset >= 0 && particleOffset % 9 === 0) {
        return Math.floor(particleOffset / 9) % 2 === 0 ? 0.75 : 0.25
      }
      return 0.5
    })

    let frame: FrameRequestCallback | undefined
    const cancelFrame = vi.fn()
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frame = callback
      return 9
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(cancelFrame)

    let mutationCallback: MutationCallback | undefined
    const disconnectObserver = vi.fn()
    vi.stubGlobal(
      "MutationObserver",
      class {
        constructor(callback: MutationCallback) {
          mutationCallback = callback
        }
        observe = vi.fn()
        disconnect = disconnectObserver
        takeRecords = vi.fn(() => [])
      }
    )

    const { default: ParticleAuthBackground } = await import("../ParticleAuthBackground")
    const { container, unmount } = render(<ParticleAuthBackground />)
    const host = container.firstElementChild as HTMLDivElement
    Object.defineProperty(host, "clientWidth", { configurable: true, value: 640 })
    Object.defineProperty(host, "clientHeight", { configurable: true, value: 360 })

    act(() => vi.runOnlyPendingTimers())
    expect(context.arc).toHaveBeenCalled()
    expect(frame).toBeDefined()

    window.dispatchEvent(new MouseEvent("mousemove", { clientX: 10, clientY: 10 }))
    const hypot = vi
      .spyOn(Math, "hypot")
      .mockReturnValueOnce(2)
      .mockReturnValueOnce(5)
      .mockReturnValueOnce(2)
      .mockReturnValueOnce(50)
    window.dispatchEvent(new MouseEvent("mousemove", { clientX: 12, clientY: 10 }))
    act(() => frame?.(1))
    act(() => frame?.(2))
    window.dispatchEvent(new MouseEvent("mousemove", { clientX: 200, clientY: 200 }))
    act(() => frame?.(3))
    expect(hypot).toHaveBeenCalledTimes(4)

    document.documentElement.style.setProperty("--primary-main", "#123456")
    document.documentElement.style.setProperty("--primary-hover", "#654321")
    act(() => {
      mutationCallback?.(
        [
          { type: "childList", attributeName: null } as MutationRecord,
          { type: "attributes", attributeName: "class" } as MutationRecord,
        ],
        {} as MutationObserver
      )
    })

    Object.defineProperty(host, "clientWidth", { configurable: true, value: 0 })
    Object.defineProperty(host, "clientHeight", { configurable: true, value: 0 })
    window.dispatchEvent(new Event("resize"))
    unmount()
    expect(cancelFrame).toHaveBeenCalled()
    expect(disconnectObserver).toHaveBeenCalledOnce()
  })
})
