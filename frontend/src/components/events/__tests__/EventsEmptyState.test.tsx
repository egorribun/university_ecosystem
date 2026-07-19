import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { EventsEmptyState } from "../EventsEmptyState"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/components/ui", () => ({
  Button: ({ children, onClick }: { children: ReactNode; onClick: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
}))

describe("EventsEmptyState", () => {
  it("moves from active events to the archive", () => {
    const onTabChange = vi.fn()
    render(<EventsEmptyState tab="active" onTabChange={onTabChange} />)

    expect(screen.getByText("events:states.emptyHint.active")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "events:tabs.archive" }))

    expect(onTabChange).toHaveBeenCalledWith("archive")
  })

  it("moves from archived events back to active events", () => {
    const onTabChange = vi.fn()
    render(<EventsEmptyState tab="archive" onTabChange={onTabChange} />)

    expect(screen.getByText("events:states.emptyHint.archive")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "events:tabs.active" }))

    expect(onTabChange).toHaveBeenCalledWith("active")
  })

  it("does not offer a tab switch for an empty personal list", () => {
    render(<EventsEmptyState tab="my" onTabChange={vi.fn()} />)

    expect(screen.getByText("events:states.emptyHint.my")).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })
})
