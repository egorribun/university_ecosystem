export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  cursor: number
  next_cursor: number | null
  has_more: boolean
}
