import { act, cleanup, fireEvent, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import MobileBottomNav from "@/components/layout/MobileBottomNav"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const marker = "__scrollTopNext"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  sessionStorage.removeItem(marker)
})

describe("MobileBottomNav optional scroll storage", () => {
  it.each(["getItem", "removeItem"] as const)(
    "keeps navigation usable when marker %s throws",
    async (method) => {
      sessionStorage.setItem(marker, "1")
      const original = Storage.prototype[method]
      vi.spyOn(Storage.prototype, method).mockImplementation(function (
        this: Storage,
        key: string
      ) {
        if (key === marker) throw new DOMException("Storage blocked", "SecurityError")
        return original.call(this, key)
      })
      const raf = vi.spyOn(window, "requestAnimationFrame")
      await renderWithRouter({
        ui: MobileBottomNav,
        path: "/dashboard",
        initialPath: "/dashboard",
        extraRoutes: [{ path: "/news", Component: MobileBottomNav }],
      })

      expect(screen.getByRole("navigation")).toBeInTheDocument()
      await act(async () => {
        fireEvent.click(screen.getByRole("link", { name: "News" }))
      })
      expect(screen.getByRole("link", { name: "News" })).toHaveAttribute("aria-current", "page")
      expect(raf).not.toHaveBeenCalled()
    }
  )

  it("keeps pointer navigation usable when saving the marker exceeds quota", async () => {
    const original = Storage.prototype.setItem
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key: string,
      value: string
    ) {
      if (key === marker) throw new DOMException("Storage full", "QuotaExceededError")
      return original.call(this, key, value)
    })
    await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
      extraRoutes: [{ path: "/news", Component: () => <div>News destination</div> }],
    })

    const link = screen.getByRole("link", { name: "News" })
    // jsdom's empty root is at its bottom, so this exercises the marker write.
    fireEvent.pointerDown(link)
    expect(setItem).toHaveBeenCalledWith(marker, "1")
    await act(async () => {
      fireEvent.click(link)
    })
    expect(await screen.findByText("News destination")).toBeInTheDocument()
    expect(sessionStorage.getItem(marker)).toBeNull()
  })
})
