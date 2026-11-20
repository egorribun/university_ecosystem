import * as v from "valibot"

import { searchText } from "@/utils/searchParams"

export const eventsSearchSchema = v.object({
  tab: searchText(),
  q: searchText(),
  dr: searchText(),
  loc: searchText(),
  sort: searchText(),
  cat: searchText(),
})
