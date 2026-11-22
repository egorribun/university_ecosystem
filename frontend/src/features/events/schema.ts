import * as v from "valibot"

import { searchChoice, searchText } from "@/utils/searchParams"
import { ALL_EVENT_CATEGORIES } from "./categories"

export const eventsSearchSchema = v.object({
  tab: searchChoice(["active", "archive", "my"]),
  q: searchText(),
  dr: searchChoice(["", "today", "week", "month"]),
  loc: searchText(),
  sort: searchChoice(["newest", "popular", "upcoming"]),
  cat: searchChoice(["all", ...ALL_EVENT_CATEGORIES.map((category) => category.id)]),
})
