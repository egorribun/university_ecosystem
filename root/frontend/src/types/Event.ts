export interface EventFile {
  id: number
  event_id: number
  file_url: string
  description: string | null
}

export interface Event {
  id: number
  title: string
  description: string | null
  title_en: string | null
  description_en: string | null
  location: string | null
  location_en: string | null
  event_type: string | null
  event_type_en: string | null
  starts_at: string
  ends_at: string
  created_by: number
  created_at: string
  is_active: boolean
  speaker: string | null
  image_url: string | null
  about: string | null
  about_en: string | null
  files: EventFile[]
  participant_count: number
  is_registered: boolean | null
  my_qr_code: string | null
}
