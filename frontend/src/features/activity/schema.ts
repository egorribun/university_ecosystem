import * as v from "valibot"
import { PERIOD_VALUES } from "./types"

/**
 * Activity route search-param schema — Wave 112 SW3 URL-sync.
 *
 * Only the period selector is URL-synced. Keeping the schema minimal means
 * refresh and share both preserve the user's view. The short `p` key matches
 * Events' `tab/q/dr/loc/sort/cat` convention (short, URL-friendly).
 */
export const activitySearchSchema = v.object({
  p: v.optional(v.picklist(PERIOD_VALUES)),
})

export type ActivitySearch = v.InferOutput<typeof activitySearchSchema>
