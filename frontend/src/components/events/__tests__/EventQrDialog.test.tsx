import { fireEvent, render, screen } from "@testing-library/react"
import type { ImgHTMLAttributes } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/components/ui/Dialog", () => ({
  default: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div role="dialog">{children}</div> : null,
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

vi.mock("react-i18next", () => ({ useTranslation: useTranslationMock }))

vi.mock("@/components/media/SmartImage", () => ({
  default: (props: ImgHTMLAttributes<HTMLImageElement> & { srcRaw: string }) => {
    const { srcRaw, alt, ...imageProps } = props
    return <img src={srcRaw} alt={alt ?? ""} {...imageProps} />
  },
}))

import { EventQrDialog } from "@/components/events/EventQrDialog"

describe("EventQrDialog", () => {
  it("does not render dialog content while closed", () => {
    render(<EventQrDialog open={false} qr="ticket:42" onClose={vi.fn()} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("reveals the QR image after it loads", () => {
    render(<EventQrDialog open qr="ticket:42" onClose={vi.fn()} />)
    const image = screen.getByRole("img")

    expect(image).toHaveClass("opacity-0")
    expect(image).toHaveAttribute(
      "src",
      "https://api.qrserver.com/v1/create-qr-code/?data=ticket%3A42&size=600x600"
    )
    expect(image).toHaveAttribute("alt", "events:card.alt.qr")
    expect(image).toHaveAttribute("loading", "eager")
    expect(image).toHaveClass("aspect-square", "opacity-0")
    fireEvent.load(image)
    expect(image).toHaveClass("opacity-100")
    expect(useTranslationMock).toHaveBeenCalledWith()
    expect(translationMock).toHaveBeenCalledWith("events:card.dialogs.qr.title")
    expect(translationMock).toHaveBeenCalledWith("events:card.alt.qr")
    expect(translationMock).toHaveBeenCalledWith("events:card.actions.closeQr")
  })

  it("resets QR loading when the QR value changes while open", () => {
    const { rerender } = render(<EventQrDialog open qr="ticket:42" onClose={vi.fn()} />)
    const image = screen.getByRole("img")
    fireEvent.load(image)
    expect(image).toHaveClass("opacity-100")

    rerender(<EventQrDialog open qr="ticket:43" onClose={vi.fn()} />)
    expect(screen.getByRole("img")).toHaveClass("opacity-0")
  })

  it("closes through the explicit close action", async () => {
    const user = (await import("@testing-library/user-event")).default.setup()
    const onClose = vi.fn()
    render(<EventQrDialog open qr="ticket:42" onClose={onClose} />)

    await user.click(screen.getByRole("button", { name: "events:card.actions.closeQr" }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
