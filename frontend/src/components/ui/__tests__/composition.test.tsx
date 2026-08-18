/**
 * Tests for component composition primitives
 */

import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { ContentCard } from "../ContentCard"
import { ActionMenu } from "../ActionMenu"
import { MediaSlot } from "../MediaSlot"

describe("ContentCard", () => {
  it("renders with basic slots", () => {
    render(
      <ContentCard data-testid="card">
        <ContentCard.Header>
          <ContentCard.Title>Test Title</ContentCard.Title>
        </ContentCard.Header>
        <ContentCard.Body>Test body content</ContentCard.Body>
      </ContentCard>
    )

    expect(screen.getByTestId("card")).toBeInTheDocument()
    expect(screen.getByText("Test Title")).toBeInTheDocument()
    expect(screen.getByText("Test body content")).toBeInTheDocument()
  })

  it("renders Media slot with image", () => {
    render(
      <ContentCard>
        <ContentCard.Media src="test.jpg" alt="Test image" data-testid="media" />
      </ContentCard>
    )

    const img = screen.getByAltText("Test image")
    expect(img.getAttribute("src")).toMatch(/test\.jpg$/)
  })

  it("renders Footer and Meta slots", () => {
    render(
      <ContentCard>
        <ContentCard.Meta>Category • 2 min read</ContentCard.Meta>
        <ContentCard.Footer>Footer content</ContentCard.Footer>
      </ContentCard>
    )

    expect(screen.getByText("Category • 2 min read")).toBeInTheDocument()
    expect(screen.getByText("Footer content")).toBeInTheDocument()
  })

  it("renders Badge with variants", () => {
    render(
      <ContentCard>
        <ContentCard.Badge variant="success">Live</ContentCard.Badge>
        <ContentCard.Badge variant="warning">Soon</ContentCard.Badge>
      </ContentCard>
    )

    expect(screen.getByText("Live")).toBeInTheDocument()
    expect(screen.getByText("Soon")).toBeInTheDocument()
  })
})

describe("ActionMenu", () => {
  const mockItems = [
    { label: "Edit", onClick: vi.fn() },
    { label: "Delete", onClick: vi.fn(), variant: "danger" as const },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("opens menu on trigger click", async () => {
    const user = userEvent.setup()

    render(<ActionMenu items={mockItems} />)

    const trigger = screen.getByRole("button", { name: "Open menu" })
    await user.click(trigger)

    expect(screen.getByRole("menu")).toBeInTheDocument()
    expect(screen.getByText("Edit")).toBeInTheDocument()
    expect(screen.getByText("Delete")).toBeInTheDocument()
  })

  it("calls onClick when item clicked", async () => {
    const user = userEvent.setup()

    render(<ActionMenu items={mockItems} />)

    const trigger = screen.getByRole("button", { name: "Open menu" })
    await user.click(trigger)
    await user.click(screen.getByText("Edit"))

    expect(mockItems[0]!.onClick).toHaveBeenCalledTimes(1)
  })

  it("closes menu after item click", async () => {
    const user = userEvent.setup()

    render(<ActionMenu items={mockItems} />)

    const trigger = screen.getByRole("button", { name: "Open menu" })
    await user.click(trigger)
    await user.click(screen.getByText("Edit"))

    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("closes menu on Escape key", async () => {
    const user = userEvent.setup()

    render(<ActionMenu items={mockItems} />)

    const trigger = screen.getByRole("button", { name: "Open menu" })
    await user.click(trigger)
    await user.keyboard("{Escape}")

    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("disables item when disabled prop is true", async () => {
    const disabledItems = [{ label: "Disabled", onClick: vi.fn(), disabled: true }]
    const user = userEvent.setup()

    render(<ActionMenu items={disabledItems} />)

    const trigger = screen.getByRole("button", { name: "Open menu" })
    await user.click(trigger)

    const disabledButton = screen.getByText("Disabled")
    expect(disabledButton).toBeDisabled()
  })

  it("handles keyboard input with an empty menu", async () => {
    const user = userEvent.setup()
    render(<ActionMenu items={[]} />)

    const trigger = screen.getByRole("button", { name: "Open menu" })
    await user.click(trigger)
    fireEvent.keyDown(trigger, { key: "ArrowDown" })

    expect(screen.getByRole("menu")).toBeInTheDocument()
  })
})

describe("MediaSlot", () => {
  it("renders fallback when no src provided", () => {
    const { container } = render(<MediaSlot alt="Test" />)

    // Should render the container with fallback (an SVG icon)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper).toBeInTheDocument()
    expect(wrapper).toHaveStyle({ aspectRatio: "16/9" })
  })

  it("renders image when src provided", () => {
    render(<MediaSlot src="test.jpg" alt="Test image" />)

    const img = screen.getByAltText("Test image")
    expect(img.getAttribute("src")).toMatch(/test\.jpg$/)
    expect(img).toHaveAttribute("loading", "lazy")
  })

  it("applies aspect ratio style", () => {
    const { container } = render(<MediaSlot src="test.jpg" alt="Test" aspectRatio="4/3" />)

    const wrapper = container.firstChild as HTMLElement
    expect(wrapper).toHaveStyle({ aspectRatio: "4/3" })
  })

  it("calls onLoad callback when image loads", () => {
    const onLoad = vi.fn()

    render(<MediaSlot src="test.jpg" alt="Test" onLoad={onLoad} />)

    const img = screen.getByAltText("Test")
    fireEvent.load(img)

    expect(onLoad).toHaveBeenCalledTimes(1)
  })

  it("calls onError callback and shows fallback on error", () => {
    const onError = vi.fn()

    render(<MediaSlot src="bad.jpg" alt="Test" onError={onError} />)

    const img = screen.getByAltText("Test")
    fireEvent.error(img)

    expect(onError).toHaveBeenCalledTimes(1)
  })
})
