import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { NewsDetailHero } from "@/components/news/NewsDetailHero"

const baseProps = {
  imageUrl: "https://picsum.photos/seed/news-detail/1200/675",
  displayTitle: "University Announces New AI Research Center",
}

describe("NewsDetailHero", () => {
  it("renders the hero image and a zoom button", () => {
    render(<NewsDetailHero {...baseProps} />)
    expect(screen.getByRole("button", { name: "news:actions.zoomImage" })).toBeInTheDocument()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders a fallback figcaption when there is no display title", () => {
    render(<NewsDetailHero {...baseProps} displayTitle="" />)
    expect(screen.getByText("news:alt.heroFallback")).toBeInTheDocument()
  })

  it("uses responsive framing for portrait, square, wide, and landscape images", () => {
    const { rerender } = render(<NewsDetailHero {...baseProps} />)
    const setDimensionsAndLoad = (width: number, height: number) => {
      const image = screen.getByRole("img")
      Object.defineProperty(image, "naturalWidth", { configurable: true, value: width })
      Object.defineProperty(image, "naturalHeight", { configurable: true, value: height })
      fireEvent.load(image)
      return image
    }

    let image = setDimensionsAndLoad(600, 1200)
    expect(image).toHaveClass("object-contain")
    expect(image.parentElement).toHaveClass("aspect-3/4")

    image = setDimensionsAndLoad(1000, 1000)
    expect(image.parentElement).toHaveClass("aspect-5/4")

    image = setDimensionsAndLoad(3000, 1000)
    expect(image.parentElement).toHaveClass("aspect-21/9")

    image = setDimensionsAndLoad(1600, 1000)
    expect(image.parentElement).toHaveClass("aspect-video")

    rerender(<NewsDetailHero {...baseProps} imageUrl={`${baseProps.imageUrl}?next=1`} />)
    expect(screen.getByRole("img").parentElement).toHaveClass("max-h-(--layout-max-modal)")
  })

  it("handles an image without measurable dimensions and an empty image URL", () => {
    const { rerender } = render(<NewsDetailHero {...baseProps} />)
    const image = screen.getByRole("img")
    Object.defineProperty(image, "naturalWidth", { configurable: true, value: 0 })
    Object.defineProperty(image, "naturalHeight", { configurable: true, value: 0 })
    fireEvent.load(image)
    expect(image).toHaveClass("object-cover")

    rerender(<NewsDetailHero imageUrl="" displayTitle="" />)
    expect(screen.queryByRole("button", { name: "news:actions.zoomImage" })).not.toBeInTheDocument()
    expect(screen.getByText("news:alt.heroFallback")).toBeInTheDocument()
  })

  it("opens and closes the lightbox", async () => {
    const user = userEvent.setup()
    render(<NewsDetailHero {...baseProps} />)
    await user.click(screen.getByRole("button", { name: "news:actions.zoomImage" }))
    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "news:actions.zoomImage" }))
    const reopenedDialog = screen.getByRole("dialog")
    const backdrop = reopenedDialog.querySelector("div.absolute.inset-0")
    expect(backdrop).not.toBeNull()
    fireEvent.click(backdrop!)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
