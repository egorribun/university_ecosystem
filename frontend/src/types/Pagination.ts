import type { PaginatedEvents } from "@/api/generated"

export type PaginatedResponse<T> = Omit<PaginatedEvents, "items"> & {
  items: T[]
}
