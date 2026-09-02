import { fireEvent, render, screen } from "@testing-library/react"
import { act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { mockOnDeactivate, focusTrapOptions } = vi.hoisted(() => ({
  mockOnDeactivate: vi.fn(),
  focusTrapOptions: { active: false, allowOutsideClick: false as boolean },
}))
const { useTranslationMock, translationMock } = vi.hoisted(() => {
  const translationMock = vi.fn((key: string) => key)
  return {
    useTranslationMock: vi.fn(() => ({
      t: translationMock,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    })),
    translationMock,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))
vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    srcRaw,
    ...props
  }: { srcRaw?: string } & React.ImgHTMLAttributes<HTMLImageElement>) => {
    return <img src={srcRaw ?? ""} alt={props.alt ?? ""} {...props} />
  },
}))
vi.mock("@/hooks/useFocusTrap", () => ({
  default: (options: { active: boolean; allowOutsideClick: boolean; onDeactivate: () => void }) => {
    focusTrapOptions.active = options.active
    focusTrapOptions.allowOutsideClick = options.allowOutsideClick
    mockOnDeactivate.mockImplementation(options.onDeactivate)
    return { current: null }
  },
}))

import { EventDetailHero, focusCloseButton } from "@/components/events/EventDetailHero"

const props = { imageUrl: "https://example.test/event.png" }

const setNaturalSize = (image: HTMLImageElement, width: number, height: number) => {
  Object.defineProperty(image, "naturalWidth", { configurable: true, value: width })
  Object.defineProperty(image, "naturalHeight", { configurable: true, value: height })
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

beforeEach(() => {
  mockOnDeactivate.mockReset()
  focusTrapOptions.active = false
  focusTrapOptions.allowOutsideClick = false
})

describe("EventDetailHero closure", () => {
  it("selects portrait, square, and landscape aspect modes from image dimensions", () => {
    const { container } = render(<EventDetailHero {...props} />)
    const image = screen.getByRole("img") as HTMLImageElement
    const hero = container.firstElementChild as HTMLElement

    expect(hero).toHaveAttribute("data-aspect-mode", "landscape")
    expect(hero).toHaveClass(
      "relative",
      "w-full",
      "overflow-hidden",
      "rounded-2xl",
      "glass-layer-elevated",
      "glass-noise",
      "border",
      "border-glass-border/(--opacity-soft)",
      "aspect-video"
    )
    expect(hero).toHaveStyle({ viewTransitionName: "events-hero" })
    expect(image).toHaveAttribute("src", props.imageUrl)
    expect(image).toHaveAttribute("alt", "events:alt.image")
    expect(image).toHaveClass("h-full", "w-full", "object-cover")
    expect(image).toHaveAttribute("loading", "eager")
    expect(image).toHaveAttribute("fetchpriority", "high")

    setNaturalSize(image, 600, 1000)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-3/4")
    expect(hero).toHaveAttribute("data-aspect-mode", "portrait")
    expect(image).toHaveClass("object-contain")

    setNaturalSize(image, 900, 900)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-square")
    expect(hero).toHaveAttribute("data-aspect-mode", "square")

    setNaturalSize(image, 1800, 900)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-video")
    expect(hero).toHaveAttribute("data-aspect-mode", "landscape")
    expect(image).toHaveClass("object-cover")

    setNaturalSize(image, 85, 100)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-square")

    setNaturalSize(image, 140, 100)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-square")

    setNaturalSize(image, 0, 0)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-square")
  })

  it("focuses the close button, keeps image clicks inside, and closes on Escape/backdrop", () => {
    vi.useFakeTimers()
    render(<EventDetailHero {...props} />)
    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    expect(focusTrapOptions).toEqual({ active: true, allowOutsideClick: true })

    act(() => {
      vi.advanceTimersByTime(50)
    })
    expect(closeButton).toHaveFocus()

    act(() => {
      mockOnDeactivate()
    })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    const dialog = screen.getByRole("dialog", { name: "events:detail.actions.zoom" })

    const lightboxImage = dialog.querySelector("img")
    expect(lightboxImage).not.toBeNull()
    expect(lightboxImage).toHaveAttribute("src", props.imageUrl)
    expect(lightboxImage).toHaveAttribute("alt", "events:alt.image")
    fireEvent.click(lightboxImage!)
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Enter" })
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    fireEvent.click(screen.getByRole("dialog"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    expect(useTranslationMock).toHaveBeenCalledWith(["events"])
    expect(translationMock).toHaveBeenCalledWith("events:detail.actions.zoom")
    expect(translationMock).toHaveBeenCalledWith("common:buttons.close")
  })

  it("cleans up the Escape listener when the lightbox closes", () => {
    const { unmount } = render(<EventDetailHero {...props} />)
    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    unmount()
  })

  it("does not focus a detached close button after unmount", () => {
    vi.useFakeTimers()
    const focusSpy = vi.spyOn(HTMLButtonElement.prototype, "focus")
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout")
    const { unmount } = render(<EventDetailHero {...props} />)
    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    unmount()

    act(() => {
      vi.advanceTimersByTime(50)
    })
    expect(focusSpy).not.toHaveBeenCalled()
    expect(clearTimeoutSpy).toHaveBeenCalled()
    focusSpy.mockRestore()
  })

  it("does not schedule focus or keyboard listeners while the lightbox is closed", () => {
    vi.useFakeTimers()
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout")
    const addEventListenerSpy = vi.spyOn(document, "addEventListener")

    render(<EventDetailHero {...props} />)

    expect(setTimeoutSpy).not.toHaveBeenCalled()
    expect(addEventListenerSpy.mock.calls.some(([type]) => type === "keydown")).toBe(false)

    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 50)
    expect(addEventListenerSpy.mock.calls.some(([type]) => type === "keydown")).toBe(true)
  })

  it("removes the Escape listener after the lightbox closes", () => {
    const removeEventListenerSpy = vi.spyOn(document, "removeEventListener")
    render(<EventDetailHero {...props} />)

    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    fireEvent.keyDown(document, { key: "Escape" })

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(removeEventListenerSpy).toHaveBeenCalledWith("keydown", expect.any(Function))
  })

  it("stops close-button clicks from bubbling through the lightbox backdrop", () => {
    const stopPropagationSpy = vi.spyOn(Event.prototype, "stopPropagation")
    render(<EventDetailHero {...props} />)

    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))

    expect(stopPropagationSpy).toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("re-evaluates image orientation after the source is replaced", () => {
    const { rerender, container } = render(
      <EventDetailHero imageUrl="https://example.test/first.png" />
    )
    const firstImage = screen.getByRole("img") as HTMLImageElement
    setNaturalSize(firstImage, 600, 1000)
    fireEvent.load(firstImage)
    expect(container.firstElementChild).toHaveAttribute("data-aspect-mode", "portrait")

    rerender(<EventDetailHero imageUrl="https://example.test/second.png" />)
    const secondImage = screen.getByRole("img") as HTMLImageElement
    setNaturalSize(secondImage, 1800, 900)
    fireEvent.load(secondImage)
    expect(container.firstElementChild).toHaveAttribute("data-aspect-mode", "landscape")
  })

  it("focuses only mounted close buttons", () => {
    const focusSpy = vi.spyOn(HTMLButtonElement.prototype, "focus")
    expect(() => focusCloseButton(null)).not.toThrow()
    const button = document.createElement("button")
    focusCloseButton(button)
    expect(focusSpy).toHaveBeenCalledTimes(1)
  })
})
