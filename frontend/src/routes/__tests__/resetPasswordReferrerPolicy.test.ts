import { describe, expect, it } from "vitest"

import { Route as ResetPasswordRoute } from "../_public/reset-password"
import { Route as ResetPasswordTokenRoute } from "../_public/reset-password.$token"

type HeadMetadata = { meta?: Array<Record<string, string>> }

/** Evaluates the route's head registration exactly as the router does for a match. */
const headMetadataOf = (route: unknown): HeadMetadata => {
  const head = (route as { options: { head?: (context: unknown) => HeadMetadata } }).options.head
  return head ? head({}) : {}
}

/**
 * AUD-178: reset links carry a single-use token in the URL. The page must
 * declare no-referrer so the token is never forwarded in a Referer header.
 */
describe("password reset pages referrer policy", () => {
  it.each([
    ["/reset-password", ResetPasswordRoute],
    ["/reset-password/$token", ResetPasswordTokenRoute],
  ])("%s declares a no-referrer meta tag", (_path, route) => {
    expect(headMetadataOf(route).meta).toContainEqual({
      name: "referrer",
      content: "no-referrer",
    })
  })
})
