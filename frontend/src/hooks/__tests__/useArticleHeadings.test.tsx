import { renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { marked } from "marked"

import { useArticleHeadings } from "../useArticleHeadings"

describe("useArticleHeadings", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("returns no entries for blank content", () => {
    expect(renderHook(() => useArticleHeadings("   ")).result.current).toEqual([])
  })

  it("extracts level-two and level-three headings while ignoring empty and other levels", () => {
    const markdown = [
      "# ignored",
      "## Getting started",
      "### **Details**",
      "#### also ignored",
      "## <span></span>",
    ].join("\n\n")

    expect(renderHook(() => useArticleHeadings(markdown)).result.current).toEqual([
      { id: "getting-started", text: "Getting started", level: 2 },
      { id: "details", text: "**Details**", level: 3 },
    ])
  })

  it("returns an empty list when Markdown lexing fails", () => {
    vi.spyOn(marked, "lexer").mockImplementation(() => {
      throw new Error("malformed markdown")
    })

    expect(renderHook(() => useArticleHeadings("## anything")).result.current).toEqual([])
  })
})
