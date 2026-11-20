import * as v from "valibot"

/**
 * Route search fields built from user-controlled URLs.
 *
 * TanStack Router JSON-parses search values, so a typed or shared link such as
 * `?q=12` arrives as the number 12 and `?q=true` as a boolean. A strict
 * `v.string()` then throws inside `validateSearch`, and the SSR route answers
 * 500 (ZAP rule 30003 found this on `/login?redirect=<number>`). These fields
 * never throw: scalar values become their text, anything else is dropped.
 */
export const searchText = () =>
  v.fallback(
    v.optional(
      v.pipe(
        v.union([v.string(), v.number(), v.boolean()]),
        v.transform((value) => String(value))
      )
    ),
    undefined
  )

/** An optional enumerated search field; unknown values are dropped. */
export const searchChoice = <const TOptions extends readonly [string, ...string[]]>(
  options: TOptions
) => v.fallback(v.optional(v.picklist(options)), undefined)
