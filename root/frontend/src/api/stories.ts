import type { components, paths } from "@/api/generated/schema"
import axios from "./client"

type StoriesListResponse =
  paths["/api/v1/stories"]["get"]["responses"]["200"]["content"]["application/json"]
export type StoryCreatePayload = components["schemas"]["StoryCreate"]
export type StoryUpdatePayload = components["schemas"]["StoryUpdate"]
type StoryResponse = components["schemas"]["StoryOut"]
type DeleteStoryResponse =
  paths["/api/v1/stories/{story_id}"]["delete"]["responses"]["200"]["content"]["application/json"]

export function fetchStories(ifNoneMatch?: string | null) {
  return axios.get<StoriesListResponse>("/api/v1/stories", {
    headers: ifNoneMatch ? { "If-None-Match": ifNoneMatch } : undefined,
    validateStatus: (status) => status === 304 || (status >= 200 && status < 300),
  })
}

export function createStory(payload: StoryCreatePayload) {
  return axios.post<StoryResponse>("/api/v1/stories", payload)
}

export function updateStory(storyId: number, payload: StoryUpdatePayload) {
  return axios.patch<StoryResponse>(`/api/v1/stories/${storyId}`, payload)
}

export function deleteStory(storyId: number) {
  return axios.delete<DeleteStoryResponse>(`/api/v1/stories/${storyId}`)
}

export function uploadStoryCover(file: File) {
  const data = new FormData()
  data.append("file", file)
  return axios.post<{ url: string }>("/api/v1/stories/upload_cover", data, {
    headers: { "Content-Type": "multipart/form-data" },
  })
}
