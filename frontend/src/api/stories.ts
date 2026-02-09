import type { components, paths } from "@/api/generated/schema"
import axios from "./client"

type StoriesListResponse =
  paths["/api/v1/stories"]["get"]["responses"]["200"]["content"]["application/json"]
export type StoryCreatePayload = components["schemas"]["StoryCreate"]
export type StoryUpdatePayload = components["schemas"]["StoryUpdate"]
type StoryResponse = components["schemas"]["StoryOut"]
type DeleteStoryResponse =
  paths["/api/v1/stories/{story_id}"]["delete"]["responses"]["200"]["content"]["application/json"]

export function fetchStories() {
  return axios.get<StoriesListResponse>("/stories", {
    validateStatus: (status: number) => status >= 200 && status < 400,
    etagCacheKey: "dashboard:stories",
  } as any)
}

export function createStory(payload: StoryCreatePayload) {
  return axios.post<StoryResponse>("/stories", payload)
}

export const updateStory = (id: string, data: Partial<StoryCreatePayload>) =>
  axios.patch<StoryResponse>(`/stories/${id}`, data)

export const deleteStory = (id: string) => axios.delete<DeleteStoryResponse>(`/stories/${id}`)

export function uploadStoryCover(file: File) {
  const data = new FormData()
  data.append("file", file)
  return axios.post<{ url: string }>("/stories/upload_cover", data, {
    headers: { "Content-Type": "multipart/form-data" },
  })
}




