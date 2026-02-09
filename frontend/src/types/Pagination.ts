import type { components } from "@/api/generated/schema"

type PaginatedEventsSchema = components["schemas"]["PaginatedEvents"]

export type PaginatedResponse<T> = Omit<PaginatedEventsSchema, "items"> & {
  items: T[]
}




