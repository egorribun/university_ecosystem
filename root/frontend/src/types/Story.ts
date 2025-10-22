export interface StoryItem {
  id: number
  title: string
  title_en?: string | null
  short_text: string
  short_text_en?: string | null
  cover_url?: string | null
  cta_url?: string | null
  published_at: string
  expires_at: string
  is_active: boolean
  created_by?: number | null
  created_at: string
}
