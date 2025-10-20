import { describe, expect, it } from "vitest"
import { buildAvatarUrl } from "@/utils/avatar"

describe("buildAvatarUrl", () => {
  it("resolves relative avatar URLs against the dev origin", () => {
    const result = buildAvatarUrl("/static/avatars/user.webp", 42, {
      baseURL: "/api",
      locationOrigin: "http://localhost:5173",
    })

    expect(result).toBe("http://localhost:5173/static/avatars/user.webp?uid=42")
  })

  it("resolves relative avatar URLs against the production backend origin", () => {
    const result = buildAvatarUrl("/static/avatars/user.webp", 99, {
      baseURL: "https://api.example.com",
    })

    expect(result).toBe("https://api.example.com/static/avatars/user.webp?uid=99")
  })

  it("returns absolute avatar URLs as-is", () => {
    const absolute = "https://cdn.example.com/avatars/user.webp"
    const result = buildAvatarUrl(absolute, 77, {
      baseURL: "https://api.example.com",
    })

    expect(result).toBe(absolute)
  })
})
