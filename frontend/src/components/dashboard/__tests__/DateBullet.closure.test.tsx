import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const useTranslationMock = vi.hoisted(() =>
  vi.fn((namespace: string) => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}:${String(options.date)}` : key,
    namespace,
  }))
)

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))

vi.mock("@/components/ui", () => ({
  Tooltip: ({ children, content }: { children: ReactNode; content: string }) => (
    <div data-tooltip={content}>{children}</div>
  ),
}))

import { DateBullet } from "@/components/dashboard/DateBullet"

describe("DateBullet closure branches", () => {
  beforeEach(() => {
    useTranslationMock.mockClear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("renders a formatted default bullet", () => {
    render(<DateBullet date="2026-06-15T14:30:00Z" locale="en-US" />)

    const bullet = screen.getByLabelText(/ariaDatePublished/)
    expect(bullet).toBeInTheDocument()
    expect(bullet).toHaveClass(
      "relative",
      "flex",
      "flex-col",
      "items-center",
      "justify-center",
      "rounded-full",
      "h-12",
      "w-12",
      "min-h-12",
      "min-w-12",
      "date-bullet-premium",
      "transition-transform",
      "duration-base",
      "hover:scale-105",
      "focus-visible:ring-2",
      "focus-visible:ring-brand",
      "focus-visible:ring-offset-1",
      "focus-visible:rounded-full"
    )
    expect(screen.getByText("15")).toHaveClass(
      "relative",
      "z-[1]",
      "font-black",
      "leading-none",
      "tracking-tight",
      "text-brand",
      "text-base"
    )
    expect(screen.getByText(/Jun/i)).toHaveClass(
      "relative",
      "z-[1]",
      "font-bold",
      "uppercase",
      "leading-tight",
      "text-brand/(--opacity-strong)",
      "text-[0.6rem]"
    )
    expect(useTranslationMock).toHaveBeenCalledWith("common")
  })

  it("uses the unknown-date fallback and compact sizing", () => {
    const { container } = render(<DateBullet locale="en-US" size="compact" />)

    expect(screen.getByText("—")).toBeInTheDocument()
    expect(screen.getByText("--")).toBeInTheDocument()
    expect(screen.getByLabelText("ariaDatePublished:dateUnknown")).toBeInTheDocument()
    const bullet = container.querySelector(".h-10.w-10")
    expect(bullet).toBeInTheDocument()
    expect(bullet).toHaveClass("min-h-10", "min-w-10")
    expect(screen.getByText("—")).toHaveClass("text-sm")
    expect(screen.getByText("--")).toHaveClass("text-[0.5rem]")
  })

  it("passes locale and complete date formatting options to the platform", () => {
    const format = vi.spyOn(Date.prototype, "toLocaleString").mockReturnValue("FORMATTED DATE")

    render(<DateBullet date="2026-06-15T14:30:00Z" locale="ru-RU" />)

    expect(format).toHaveBeenCalledWith("ru-RU", {
      day: "2-digit",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
    expect(screen.getByLabelText("ariaDatePublished:FORMATTED DATE")).toBeInTheDocument()
  })

  it("keeps the default size when size is omitted", () => {
    const { container } = render(<DateBullet date="2026-06-15T14:30:00Z" locale="en-US" />)

    expect(container.querySelector(".h-12.w-12.min-h-12.min-w-12")).toBeInTheDocument()
    expect(container.querySelector(".h-10.w-10")).not.toBeInTheDocument()
  })
})
