import * as v from "valibot"
import { describe, expect, it } from "vitest"

import { searchChoice, searchText } from "@/utils/searchParams"

describe("searchText", () => {
  const schema = v.object({ q: searchText() })

  it("keeps strings and turns JSON-parsed scalars back into their text", () => {
    expect(v.parse(schema, { q: "lecture" }).q).toBe("lecture")
    expect(v.parse(schema, { q: 12 }).q).toBe("12")
    expect(v.parse(schema, { q: 2147483648 }).q).toBe("2147483648")
    expect(v.parse(schema, { q: false }).q).toBe("false")
  })

  it("drops values that are not text instead of throwing", () => {
    for (const q of [null, { nested: "x" }, ["a"]]) {
      expect(() => v.parse(schema, { q })).not.toThrow()
      expect(v.parse(schema, { q }).q).toBeUndefined()
    }
    expect(v.parse(schema, {}).q).toBeUndefined()
  })
})

describe("searchChoice", () => {
  const schema = v.object({ sort: searchChoice(["newest", "popular"]) })

  it("keeps a listed option and drops anything else", () => {
    expect(v.parse(schema, { sort: "popular" }).sort).toBe("popular")
    expect(v.parse(schema, { sort: "oldest" }).sort).toBeUndefined()
    expect(v.parse(schema, { sort: 12 }).sort).toBeUndefined()
    expect(v.parse(schema, {}).sort).toBeUndefined()
  })
})
