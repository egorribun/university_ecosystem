import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

let resolveMotion: ((module: Record<string, unknown>) => void) | undefined
vi.mock(
  "framer-motion",
  () =>
    new Promise<Record<string, unknown>>((resolve) => {
      resolveMotion = resolve
    })
)

describe("PageTransition unmount safety", () => {
  it("ignores a motion module that resolves after unmount", async () => {
    const { default: PageTransition } = await import("@/components/motion/PageTransition")
    const view = render(
      <PageTransition>
        <div>temporary child</div>
      </PageTransition>
    )

    expect(screen.getByText("temporary child")).toBeInTheDocument()
    await waitFor(() => expect(resolveMotion).toBeTypeOf("function"))
    view.unmount()
    resolveMotion?.({})
    await Promise.resolve()

    expect(screen.queryByText("temporary child")).not.toBeInTheDocument()
  })
})
