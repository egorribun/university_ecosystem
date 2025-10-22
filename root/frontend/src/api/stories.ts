import axios from "./client"
import type { StoryItem } from "@/types/Story"

export type StoryCreatePayload = {
  title: string
  short_text: string
  title_en?: string
  short_text_en?: string
  cover_url?: string | null
  cta_url?: string | null
  published_at?: string | null
  expires_at?: string | null
  is_active?: boolean
}

export type StoryUpdatePayload = Partial<StoryCreatePayload>

export function fetchStories(ifNoneMatch?: string | null) {
  return axios.get<StoryItem[]>("/stories", {
    headers: ifNoneMatch ? { "If-None-Match": ifNoneMatch } : undefined,
    validateStatus: (status) => status === 304 || (status >= 200 && status < 300),
  })
}

export function createStory(payload: StoryCreatePayload) {
  return axios.post<StoryItem>("/stories", payload)
}

export function updateStory(storyId: number, payload: StoryUpdatePayload) {
  return axios.patch<StoryItem>(`/stories/${storyId}`, payload)
}

export function deleteStory(storyId: number) {
  return axios.delete<{ ok: boolean }>(`/stories/${storyId}`)
}

export function uploadStoryCover(file: File) {
  const data = new FormData()
  data.append("file", file)
  return axios.post<{ url: string }>("/stories/upload_cover", data, {
    headers: { "Content-Type": "multipart/form-data" },
  })
}
