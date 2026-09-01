import { fireEvent, render, screen } from "@testing-library/react"
import { act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { mockOnDeactivate } = vi.hoisted(() => ({ mockOnDeactivate: vi.fn() }))
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
  }: { srcRaw?: string } & React.ImgHTMLAttributes<HTMLImageElement>) => (
    <img src={srcRaw ?? ""} alt={props.alt ?? ""} {...props} />
  ),
}))
vi.mock("@/hooks/useFocusTrap", () => ({
  default: (options: { onDeactivate: () => void }) => {
    mockOnDeactivate.mockImplementation(options.onDeactivate)
    return { current: null }
  },
}))

import { EventDetailHero } from "@/components/events/EventDetailHero"

const props = { imageUrl: "https://example.test/event.png" }

const setNaturalSize = (image: HTMLImageElement, width: number, height: number) => {
  Object.defineProperty(image, "naturalWidth", { configurable: true, value: width })
  Object.defineProperty(image, "naturalHeight", { configurable: true, value: height })
}

afterEach(() => {
  vi.useRealTimers()
})

beforeEach(() => {
  mockOnDeactivate.mockReset()
})

describe("EventDetailHero closure", () => {
  it("selects portrait, square, and landscape aspect modes from image dimensions", () => {
    const { container } = render(<EventDetailHero {...props} />)
    const image = screen.getByRole("img") as HTMLImageElement
    const hero = container.firstElementChild as HTMLElement

    expect(image).toHaveAttribute("src", props.imageUrl)
    expect(image).toHaveAttribute("alt", "events:alt.image")
    expect(image).toHaveAttribute("loading", "eager")
    expect(image).toHaveAttribute("fetchpriority", "high")

    setNaturalSize(image, 600, 1000)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-3/4")
    expect(image).toHaveClass("object-contain")

    setNaturalSize(image, 900, 900)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-square")

    setNaturalSize(image, 1800, 900)
    fireEvent.load(image)
    expect(hero).toHaveClass("aspect-video")
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
    const dialog = screen.getByRole("dialog")

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
    const { unmount } = render(<EventDetailHero {...props} />)
    fireEvent.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    unmount()

    act(() => {
      vi.advanceTimersByTime(50)
    })
    expect(focusSpy).not.toHaveBeenCalled()
    focusSpy.mockRestore()
  })
})
