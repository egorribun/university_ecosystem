import { describe, expect, it, vi } from "vitest"
import { getNavigationConfig } from "@/config/navigation"

describe("getNavigationConfig", () => {
  it("returns the common navigation for regular users", () => {
    const t = vi.fn((key: string) => key)
    const items = getNavigationConfig(t, "student")

    expect(items).toHaveLength(6)
    expect(items.map((item) => item.to)).toEqual([
      "/dashboard",
      "/news",
      "/schedule",
      "/events",
      "/activity",
      "/map",
    ])
    expect(t).toHaveBeenCalledWith("navigation:menu.dashboard")
  })

  it("adds every admin destination for the admin role", () => {
    const items = getNavigationConfig((key) => key, "admin")

    expect(items).toHaveLength(11)
    expect(items.slice(6).map((item) => item.to)).toEqual([
      "/admin/notifications",
      "/admin/stories",
      "/admin/users",
      "/admin/feature-flags",
      "/admin/audit",
    ])
  })
})
