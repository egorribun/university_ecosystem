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
  return listStoriesApiV1StoriesGet({
    // @ts-ignore - custom extension for etag interceptor
    etagCacheKey: "dashboard:stories",
  })
}

export function createStory(payload: StoryCreatePayload) {
  return createStoryApiV1StoriesPost({ body: payload })
}

export const updateStory = (id: string, data: StoryUpdatePayload) =>
  updateStoryApiV1StoriesStoryIdPatch({
    path: { story_id: id },
    body: data,
  })

export const deleteStory = (id: string) =>
  deleteStoryApiV1StoriesStoryIdDelete({
    path: { story_id: id },
  })

export async function uploadStoryCover(file: File) {
  const { data } = await uploadStoryCoverApiV1StoriesUploadCoverPost({
    body: { file },
  })
  if (!data) throw new Error("Upload failed")
  return data
}
