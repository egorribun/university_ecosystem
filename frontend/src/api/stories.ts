import {
  createStoryApiV1StoriesPost,
  deleteStoryApiV1StoriesStoryIdDelete,
  listStoriesApiV1StoriesGet,
  updateStoryApiV1StoriesStoryIdPatch,
  uploadStoryCoverApiV1StoriesUploadCoverPost,
} from "@/api/generated"
import type { StoryCreate, StoryUpdate } from "@/api/generated"

export type StoryCreatePayload = StoryCreate
export type StoryUpdatePayload = StoryUpdate

export function fetchStories() {
  const options = {
    etagCacheKey: "dashboard:stories",
    throwOnError: true as const,
    validateStatus: (status: number) => (status >= 200 && status < 300) || status === 304,
  }
  return listStoriesApiV1StoriesGet(options)
}

export function createStory(payload: StoryCreatePayload) {
  return createStoryApiV1StoriesPost({ body: payload, throwOnError: true })
}

export const updateStory = (id: string, data: StoryUpdatePayload) =>
  updateStoryApiV1StoriesStoryIdPatch({
    path: { story_id: id },
    body: data,
    throwOnError: true,
  })

export const deleteStory = (id: string) =>
  deleteStoryApiV1StoriesStoryIdDelete({
    path: { story_id: id },
    throwOnError: true,
  })

export async function uploadStoryCover(file: File) {
  const { data } = await uploadStoryCoverApiV1StoriesUploadCoverPost({
    body: { file },
  })
  if (!data) throw new Error("Upload failed")
  return data
}
