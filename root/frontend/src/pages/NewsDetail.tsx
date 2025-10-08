import { useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import DOMPurify from "dompurify"
import { useMemo } from "react"
import { Box, Typography, CircularProgress } from "@mui/material"
import api from "@/api/client"
import { resolveMediaUrl } from "@/utils/media"
import SmartImage from "@/components/SmartImage"

async function fetchNews(id: string) {
  const { data } = await api.get(`/news/${id}`)
  return data as {
    id: number
    title: string
    body_html?: string
    cover_url?: string
    created_at?: string
  }
}

export default function NewsDetail() {
  const { id = "" } = useParams()
  const query = useQuery({
    queryKey: ["news", id],
    queryFn: () => fetchNews(id),
    enabled: !!id,
    staleTime: 60000,
    retry: 1,
  })
  const sanitized = useMemo(
    () => DOMPurify.sanitize(query.data?.body_html || "", { USE_PROFILES: { html: true } }),
    [query.data?.body_html],
  )
  if (query.isLoading)
    return (
      <Box sx={{ minHeight: "40vh", display: "grid", placeItems: "center" }}>
        <CircularProgress />
      </Box>
    )
  if (query.isError || !query.data)
    return (
      <Box sx={{ p: 2 }}>
        <Typography color="error">Не удалось загрузить новость.</Typography>
      </Box>
    )
  const cover = resolveMediaUrl(query.data.cover_url)
  return (
    <Box sx={{ display: "grid", gap: 2, p: { xs: 1.5, md: 2 } }}>
      {!!cover && (
        <Box sx={{ width: "100%", borderRadius: 2, overflow: "hidden" }}>
          <SmartImage
            srcRaw={cover}
            alt={query.data.title || "Обложка"}
            style={{ width: "100%", height: "auto", objectFit: "cover", display: "block" }}
          />
        </Box>
      )}
      <Typography variant="h4" sx={{ fontWeight: 900 }}>
        {query.data.title}
      </Typography>
      <Box sx={{ "& img": { maxWidth: "100%", height: "auto" } }} dangerouslySetInnerHTML={{ __html: sanitized }} />
    </Box>
  )
}
