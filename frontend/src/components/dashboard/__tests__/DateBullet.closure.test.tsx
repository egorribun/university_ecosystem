import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}:${String(options.date)}` : key,
  }),
}))

vi.mock("@/components/ui", () => ({
  Tooltip: ({ children, content }: { children: ReactNode; content: string }) => (
    <div data-tooltip={content}>{children}</div>
  ),
}))

import { DateBullet } from "@/components/dashboard/DateBullet"

describe("DateBullet closure branches", () => {
  it("renders a formatted default bullet", () => {
    render(<DateBullet date="2026-06-15T14:30:00Z" locale="en-US" />)

    expect(screen.getByText("15")).toBeInTheDocument()
    expect(screen.getByLabelText(/ariaDatePublished/)).toBeInTheDocument()
    expect(screen.getByText(/Jun/i)).toBeInTheDocument()
  })

  it("uses the unknown-date fallback and compact sizing", () => {
    const { container } = render(<DateBullet locale="en-US" size="compact" />)

    expect(screen.getByText("—")).toBeInTheDocument()
    expect(screen.getByText("--")).toBeInTheDocument()
    expect(screen.getByLabelText("ariaDatePublished:dateUnknown")).toBeInTheDocument()
    expect(container.querySelector(".h-10.w-10")).toBeInTheDocument()
  })
})
