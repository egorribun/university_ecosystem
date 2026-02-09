import { describe, it, expect } from "vitest"
import { cn } from "../cn"

describe("cn utility", () => {
  it("should merge class strings", () => {
    expect(cn("a", "b")).toBe("a b")
  })

  it("should handle conditional classes", () => {
    const isFalse = false
    const isTrue = true
    expect(cn("a", isFalse && "b", "c")).toBe("a c")
    expect(cn("a", isTrue && "b", "c")).toBe("a b c")
  })

  it("should merge tailwind classes correctly (tailwind-merge)", () => {
    // Without tailwind-merge, this would be 'p-4 p-2'
    expect(cn("p-4", "p-2")).toBe("p-2")
    expect(cn("p-2", "px-4")).toBe("p-2 px-4") // Specific override wins
    expect(cn("px-4 p-4", "p-2")).toBe("p-2") // Absolute override wins
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500")
  })

  it("should handle objects and arrays", () => {
    expect(cn({ "bg-red": true, "text-white": false }, ["p-4", "m-2"])).toBe("bg-red p-4 m-2")
  })
})
