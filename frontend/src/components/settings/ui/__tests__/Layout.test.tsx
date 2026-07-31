import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

import {
  AccordionSection,
  Divider,
  SectionCard,
  SectionSubtitle,
  SectionTitle,
  SessionItem,
  Tab,
  Tabs,
} from "@/components/settings/ui/Layout"

describe("settings layout primitives", () => {
  beforeEach(() => {
    const globalWithCss = globalThis as {
      CSS?: { escape?: (value: string) => string }
    }
    if (!globalWithCss.CSS) {
      globalWithCss.CSS = { escape: (value: string) => value }
    } else if (!globalWithCss.CSS.escape) {
      globalWithCss.CSS.escape = (value: string) => value
    }
  })

  it("renders cards, titles, subtitles, sessions, and dividers with their variants", () => {
    render(
      <>
        <SectionCard component="article" className="custom-card" data-testid="card">
          card content
        </SectionCard>
        <SectionCard data-testid="default-card">default card</SectionCard>
        <SectionTitle data-testid="default-title">Default heading</SectionTitle>
        <SectionTitle component="h3" variant="subtitle2" data-testid="subtitle2">
          Small heading
        </SectionTitle>
        <SectionTitle variant="h6" data-testid="h6">
          Large heading
        </SectionTitle>
        <SectionTitle variant="unknown" data-testid="fallback-title">
          Fallback heading
        </SectionTitle>
        <SectionSubtitle variant="caption" data-testid="caption">
          Caption
        </SectionSubtitle>
        <SectionSubtitle data-testid="default-subtitle">Default subtitle</SectionSubtitle>
        <SectionSubtitle variant="unknown" data-testid="fallback-subtitle">
          Fallback subtitle
        </SectionSubtitle>
        <SessionItem data-testid="active-session">Active</SessionItem>
        <SessionItem revoked data-testid="revoked-session">
          Revoked
        </SessionItem>
        <Divider />
        <Divider flexItem />
      </>
    )

    expect(screen.getByTestId("card").tagName).toBe("ARTICLE")
    expect(screen.getByTestId("card")).toHaveClass("custom-card")
    expect(screen.getByTestId("default-card")).toHaveClass("rounded-2xl")
    expect(screen.getByTestId("default-title")).toHaveClass("text-base")
    expect(screen.getByTestId("subtitle2")).toHaveClass("text-sm")
    expect(screen.getByTestId("h6")).toHaveClass("text-lg")
    expect(screen.getByTestId("fallback-title")).toHaveClass("text-base")
    expect(screen.getByTestId("caption")).toHaveClass("text-xs")
    expect(screen.getByTestId("fallback-subtitle")).toHaveClass("text-sm")
    expect(screen.getByTestId("active-session")).toHaveAttribute("data-revoked", "false")
    expect(screen.getByTestId("revoked-session")).toHaveAttribute("data-revoked", "true")
    expect(screen.getByTestId("revoked-session")).toHaveStyle({ transform: "translateY(0)" })
    const separators = screen.getAllByRole("separator")
    expect(separators[0]).not.toHaveClass("self-stretch")
    expect(separators[1]).toHaveClass("self-stretch")
  })

  it("expands and collapses accordion sections with optional subtitles", async () => {
    const user = userEvent.setup()
    render(
      <>
        <AccordionSection title="Collapsed" subtitle="Details">
          <span>Collapsed body</span>
        </AccordionSection>
        <AccordionSection title="Expanded" defaultExpanded>
          <span>Expanded body</span>
        </AccordionSection>
      </>
    )

    const collapsedButton = screen.getByRole("button", { name: /Collapsed Details/ })
    expect(collapsedButton.nextElementSibling).toHaveStyle({ maxHeight: "0px" })
    await user.click(collapsedButton)
    expect(collapsedButton.nextElementSibling).toHaveStyle({ maxHeight: "2000px" })
    await user.click(collapsedButton)
    expect(collapsedButton.nextElementSibling).toHaveStyle({ maxHeight: "0px" })

    const expandedButton = screen.getByRole("button", { name: "Expanded" })
    expect(expandedButton.nextElementSibling).toHaveStyle({ maxHeight: "2000px" })
  })

  it("supports tab clicks, roving focus, and all ARIA keyboard directions", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <Tabs value={0} onChange={onChange} panelId="settings" ariaLabel="Settings sections">
        <Tab label="General" />
        <Tab label="Security" />
        <Tab label="Sessions" />
      </Tabs>
    )

    const tablist = screen.getByRole("tablist", { name: "Settings sections" })
    const tabs = screen.getAllByRole("tab")
    expect(tabs[0]).toHaveAttribute("aria-selected", "true")
    expect(tabs[0]).toHaveAttribute("aria-controls", "settings")
    expect(tabs[0]).toHaveAttribute("tabindex", "0")
    expect(tabs[1]).toHaveAttribute("tabindex", "-1")
    expect(tabs[0]).toHaveTextContent("General")

    await user.click(tabs[1]!)
    expect(onChange).toHaveBeenLastCalledWith(null, 1)

    fireEvent.keyDown(tablist, { key: "ArrowRight" })
    fireEvent.keyDown(tablist, { key: "ArrowLeft" })
    fireEvent.keyDown(tablist, { key: "Home" })
    fireEvent.keyDown(tablist, { key: "End" })
    fireEvent.keyDown(tablist, { key: "PageDown" })
    expect(onChange.mock.calls).toEqual([
      [null, 1],
      [null, 1],
      [null, 2],
      [null, 0],
      [null, 2],
    ])
    await waitFor(() => expect(document.activeElement).toBe(tabs[2]))
  })

  it("uses a generated panel id, handles single/non-element children, and ignores keys", () => {
    const onChange = vi.fn()
    const invalidChildView = render(
      <Tabs value={0} onChange={onChange}>
        {"not a tab"}
      </Tabs>
    )

    const tablist = invalidChildView.getByRole("tablist")
    fireEvent.keyDown(tablist, { key: "ArrowRight" })
    expect(onChange).not.toHaveBeenCalled()

    invalidChildView.unmount()
    render(
      <Tabs value={0} onChange={onChange}>
        <Tab label="Only" />
      </Tabs>
    )
    const tab = screen.getByRole("tab", { name: "Only" })
    expect(tab).toHaveAttribute("aria-controls")

    const missingTargetView = render(
      <Tabs value={0} onChange={onChange} panelId="missing-target">
        <Tab label="Present" />
        {null}
      </Tabs>
    )
    fireEvent.keyDown(missingTargetView.container.querySelector('[role="tablist"]')!, {
      key: "ArrowRight",
    })
    expect(onChange).toHaveBeenCalledWith(null, 1)
    onChange.mockClear()

    render(<Tab label="Standalone" selected={false} layoutId="custom-layout" onClick={onChange} />)
    const standalone = screen.getByRole("tab", { name: "Standalone" })
    expect(standalone).toHaveAttribute("aria-selected", "false")
    expect(standalone).toHaveAttribute("tabindex", "-1")
    fireEvent.click(standalone)
    expect(onChange).toHaveBeenCalledOnce()
  })

  it("ignores a deferred focus request after the tablist unmounts", async () => {
    const view = render(
      <Tabs value={0} onChange={vi.fn()} panelId="unmounted">
        <Tab label="First" />
        <Tab label="Second" />
      </Tabs>
    )
    const tablist = view.container.querySelector('[role="tablist"]')!
    fireEvent.keyDown(tablist, { key: "ArrowRight" })
    view.unmount()
    await Promise.resolve()
  })
})
