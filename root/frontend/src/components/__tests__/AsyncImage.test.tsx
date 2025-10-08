import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import AsyncImage from "../AsyncImage"

describe("AsyncImage", () => {
  const src = "https://example.com/image.png"

  it("renders skeleton while loading and hides it after load", () => {
    render(<AsyncImage src={src} alt="test" sx={{ width: 200, height: 120 }} />)

    expect(screen.getByTestId("async-image-skeleton")).toBeInTheDocument()

    const image = screen.getByTestId("async-image-img") as HTMLImageElement
    fireEvent.load(image)

    expect(screen.queryByTestId("async-image-skeleton")).not.toBeInTheDocument()
  })

  it("displays fallback on error", () => {
    render(<AsyncImage src={src} alt="error" sx={{ width: 200, height: 120 }} />)

    const image = screen.getByTestId("async-image-img") as HTMLImageElement
    fireEvent.error(image)

    expect(screen.getByTestId("async-image-fallback")).toBeInTheDocument()
  })

  it("forces reload when version changes", () => {
    const { rerender } = render(
      <AsyncImage src={src} version={1} alt="version" sx={{ width: 120, height: 120 }} />,
    )

    const image = screen.getByTestId("async-image-img") as HTMLImageElement
    fireEvent.load(image)

    expect(screen.queryByTestId("async-image-skeleton")).not.toBeInTheDocument()

    rerender(<AsyncImage src={src} version={2} alt="version" sx={{ width: 120, height: 120 }} />)

    expect(screen.getByTestId("async-image-skeleton")).toBeInTheDocument()
  })
})
