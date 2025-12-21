import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import BackToTop from "../BackToTop"
import i18n from "../../i18n/config"

const getLabel = () => i18n.t("common:buttons.backToTop")

const setScrollY = (value: number) => {
  Object.defineProperty(window, "scrollY", { value, configurable: true })
  Object.defineProperty(window, "pageYOffset", { value, configurable: true })
}

describe("BackToTop", () => {
  beforeEach(() => {
    setScrollY(0)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("does not render button when not scrolled", () => {
    render(<BackToTop />)
    const button = screen.queryByRole("button", { name: getLabel() })
    expect(button).not.toBeInTheDocument()
  })

  it("renders button after scrolling past threshold", async () => {
    render(<BackToTop />)

    setScrollY(500)
    fireEvent.scroll(window)

    await waitFor(() => {
      const button = screen.getByRole("button", { name: getLabel() })
      expect(button).toBeInTheDocument()
    })
  })

  it("hides button when scrolled back to top", async () => {
    render(<BackToTop />)

    setScrollY(500)
    fireEvent.scroll(window)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: getLabel() })).toBeInTheDocument()
    })

    setScrollY(0)
    fireEvent.scroll(window)

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: getLabel() })).not.toBeInTheDocument()
    })
  })

  it("scrolls smoothly to top when clicked", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => { })
    render(<BackToTop />)

    setScrollY(500)
    fireEvent.scroll(window)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: getLabel() })).toBeInTheDocument()
    })

    const button = screen.getByRole("button", { name: getLabel() })
    fireEvent.click(button)

    expect(scrollTo).toHaveBeenCalledTimes(1)
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
  })
})

