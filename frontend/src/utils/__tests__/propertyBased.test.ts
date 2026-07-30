import fc from "fast-check"
import { describe, expect, it } from "vitest"
import { formatCurrency, formatDate, formatNumber, getPluralCategory } from "@/i18n/formatters"
import { sanitizeArticleHtml } from "@/utils/sanitizeArticleHtml"
import { sanitizeEmailAddress, sanitizeHttpUrl, sanitizeTelegramUrl } from "@/utils/sanitize"

const telegramUsernameArbitrary = fc
  .array(
    fc.constantFrom(
      ..."abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" // pragma: allowlist secret
    ),
    {
      minLength: 5,
      maxLength: 32,
    }
  )
  .map((characters) => characters.join(""))

describe("property-based utility contracts", () => {
  it("accepts only trimmed email addresses matching the public shape", () => {
    fc.assert(
      fc.property(fc.string(), (value) => {
        const result = sanitizeEmailAddress(value)

        expect(result === "" || result === value.trim()).toBe(true)
        if (result !== "") {
          expect(result).toMatch(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)
        }
      })
    )
  })

  it("normalizes every valid generated Telegram username to t.me", () => {
    fc.assert(
      fc.property(telegramUsernameArbitrary, (username) => {
        expect(sanitizeTelegramUrl(`@${username}`)).toBe(`https://t.me/${username}`)
      })
    )
  })

  it("never returns a non-http URL or credentials from URL sanitization", () => {
    fc.assert(
      fc.property(fc.string(), (value) => {
        const result = sanitizeHttpUrl(value)
        if (result !== null) {
          const parsed = new URL(result)
          expect(["http:", "https:"]).toContain(parsed.protocol)
          expect(parsed.username).toBe("")
          expect(parsed.password).toBe("")
        }
      })
    )
  })

  it("removes generated active-content fragments from article HTML", () => {
    const dangerousFragment = fc.constantFrom(
      "<script>alert(1)</script>",
      '<img src="javascript:alert(1)" onerror="alert(1)">',
      '<a href="vbscript:alert(1)">link</a>',
      '<p onclick="alert(1)">text</p>',
      '<iframe src="https://evil.example"></iframe>',
      '<img src="data:text/html;base64,Zm9v">'
    )

    fc.assert(
      fc.property(fc.array(dangerousFragment, { minLength: 1, maxLength: 8 }), (fragments) => {
        const result = sanitizeArticleHtml(fragments.join(""))
        expect(result).not.toMatch(/<script|<iframe|javascript:|vbscript:|onerror|onclick/i)
      })
    )
  })

  it("keeps article sanitization idempotent", () => {
    const htmlFragment = fc.oneof(
      fc.string(),
      fc.constantFrom(
        "<p>safe text</p>",
        '<img src="data:image/png;base64,Zm9v">',
        '<a href="/news/42">news</a>',
        "<script>alert(1)</script>",
        '<div onclick="alert(1)">click</div>',
        '<iframe src="https://evil.example"></iframe>'
      )
    )

    fc.assert(
      fc.property(fc.array(htmlFragment, { maxLength: 8 }), (fragments) => {
        const once = sanitizeArticleHtml(fragments.join(""))
        expect(sanitizeArticleHtml(once)).toBe(once)
      })
    )
  })

  it("keeps URL sanitization idempotent for every generated input", () => {
    fc.assert(
      fc.property(fc.string(), (value) => {
        const once = sanitizeHttpUrl(value)
        const twice = sanitizeHttpUrl(once ?? "")
        expect(twice).toBe(once)
      })
    )
  })

  it("keeps locale formatters total for generated finite values", () => {
    fc.assert(
      fc.property(fc.integer(), (value) => {
        expect(formatNumber("en", value)).toEqual(expect.any(String))
        expect(formatCurrency("en", value, "USD")).toEqual(expect.any(String))
        expect(getPluralCategory("en", value)).toEqual(expect.any(String))
        expect(formatDate("en", new Date(Date.UTC(2020, 0, 1, 12, 0, 0) + value))).toEqual(
          expect.any(String)
        )
      })
    )
  })
})
