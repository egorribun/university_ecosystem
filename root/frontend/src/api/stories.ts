import axios from "./client"
import type { StoryItem } from "@/types/Story"

export function fetchStories(ifNoneMatch?: string | null) {
  return axios.get<StoryItem[]>("/stories", {
    headers: ifNoneMatch ? { "If-None-Match": ifNoneMatch } : undefined,
    validateStatus: (status) => status === 304 || (status >= 200 && status < 300),
  })
}
