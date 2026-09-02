import { fireEvent, render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/components/ui/Dialog", () => ({
  default: ({ open, children }: { open: boolean; children: React.ReactNode }) => (
    <div role="dialog" data-open={String(open)}>
      {children}
    </div>
  ),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    srcRaw,
    alt,
    ...props
  }: { srcRaw: string } & React.ImgHTMLAttributes<HTMLImageElement>) => (
    <img {...props} src={srcRaw} alt={alt ?? ""} />
  ),
}))

import { EventQrDialog } from "@/components/events/EventQrDialog"

describe("EventQrDialog mutation contracts", () => {
  it("starts with a hidden QR image during server rendering", () => {
    const markup = renderToString(<EventQrDialog open qr="ticket:42" onClose={vi.fn()} />)

    expect(markup).toContain("opacity-0")
    expect(markup).not.toContain("opacity-100")
  })

  it("shows the loading indicator until the QR image emits load", () => {
    render(<EventQrDialog open qr="ticket:42" onClose={vi.fn()} />)
    const image = screen.getByRole("img")

    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
    fireEvent.load(image)
    expect(document.querySelector(".animate-spin")).not.toBeInTheDocument()
  })

  it("does not reset a loaded image merely because the dialog closes", () => {
    const { rerender } = render(<EventQrDialog open qr="ticket:42" onClose={vi.fn()} />)
    const image = screen.getByRole("img")
    fireEvent.load(image)
    expect(image).toHaveClass("opacity-100")

    rerender(<EventQrDialog open={false} qr="ticket:42" onClose={vi.fn()} />)

    expect(screen.getByRole("img")).toHaveClass("opacity-100")
  })
})
