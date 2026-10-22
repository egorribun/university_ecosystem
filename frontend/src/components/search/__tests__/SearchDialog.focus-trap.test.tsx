import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { SearchDialog } from "@/components/search/SearchDialog"

/**
 * AUD-053 wiring contract: the search modal is role=dialog + aria-modal, so it
 * must contain focus with the shared useFocusTrap hook and hand focus back to
 * the opener on close. focus-trap is replaced here because jsdom has no layout
 * and the real library cannot find tabbable nodes in it.
 */
const focusTrap = vi.hoisted(() => ({
  containers: [] as HTMLElement[],
  options: [] as Array<Record<string, unknown>>,
  activate: vi.fn(),
  deactivate: vi.fn(),
}))

vi.mock("focus-trap", () => ({
  createFocusTrap: (container: HTMLElement, options: Record<string, unknown>) => {
    focusTrap.containers.push(container)
    focusTrap.options.push(options)
    return { activate: focusTrap.activate, deactivate: focusTrap.deactivate }
  },
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/api/client", () => ({ default: { get: vi.fn() } }))

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SearchDialog />
    </QueryClientProvider>
  )
}

describe("SearchDialog focus containment", () => {
  beforeEach(() => {
    focusTrap.containers.length = 0
    focusTrap.options.length = 0
    focusTrap.activate.mockReset()
    focusTrap.deactivate.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it("activates a focus trap around the dialog panel while it is open", () => {
    renderDialog()
    fireEvent.keyDown(document, { key: "k", ctrlKey: true })

    const dialog = screen.getByRole("dialog")
    expect(focusTrap.activate).toHaveBeenCalledOnce()
    expect(focusTrap.containers.at(-1)).toBe(dialog)
    expect(focusTrap.options.at(-1)).toMatchObject({
      escapeDeactivates: true,
      returnFocusOnDeactivate: true,
    })
  })

  it("releases the trap when the dialog closes", () => {
    renderDialog()
    fireEvent.keyDown(document, { key: "k", ctrlKey: true })
    expect(focusTrap.deactivate).not.toHaveBeenCalled()

    fireEvent.keyDown(document, { key: "Escape" })

    expect(focusTrap.deactivate).toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("does not trap focus while the dialog is closed", () => {
    renderDialog()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(focusTrap.activate).not.toHaveBeenCalled()
  })
})
