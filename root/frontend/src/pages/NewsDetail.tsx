import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import DOMPurify from "dompurify"
import { Box, Fade, Skeleton, Typography } from "@mui/material"

import api from "@/api/client"
import AsyncImage from "@/components/AsyncImage"
import { resolveMediaUrl } from "@/utils/media"

type NewsResponse = {
  id: number
  title: string
  body_html?: string
  cover_url?: string
  created_at?: string
  updated_at?: string
}

async function fetchNews(id: string) {
  const { data } = await api.get(`/news/${id}`)
  return data as NewsResponse
}

export default function NewsDetail() {
  const { id = "" } = useParams()
  const query = useQuery({
    queryKey: ["news", id],
    queryFn: () => fetchNews(id),
    enabled: Boolean(id),
    staleTime: 60_000,
    retry: 1,
  })

  const sanitized = useMemo(
    () => DOMPurify.sanitize(query.data?.body_html || "", { USE_PROFILES: { html: true } }),
    [query.data?.body_html],
  )

  const isLoading = query.isLoading
  const isError = query.isError || !query.data
  const coverUrl = query.data?.cover_url
    ? resolveMediaUrl(query.data.cover_url, import.meta.env.VITE_BACKEND_ORIGIN)
    : ""
  const imageVersion = query.data?.updated_at ? Date.parse(query.data.updated_at) : undefined

  return (
    <Box sx={{ display: "grid", gap: 2, p: { xs: 1.5, md: 2 }, minHeight: "40vh" }}>
      {isLoading && (
        <>
          <Skeleton variant="rectangular" height={240} sx={{ borderRadius: 2 }} />
          <Skeleton height={48} width="60%" />
          <Skeleton height={24} />
          <Skeleton height={24} width="90%" />
        </>
      )}

      {!isLoading && isError && (
        <Typography color="error">Не удалось загрузить новость.</Typography>
      )}

      {!isLoading && !isError && query.data && (
        <Fade in timeout={300}>
          <Box sx={{ display: "grid", gap: 2 }}>
            <Box sx={{ width: "100%", borderRadius: 2, overflow: "hidden", position: "relative", minHeight: 220 }}>
              <AsyncImage
                src={coverUrl}
                alt={query.data.title || "Обложка новости"}
                version={imageVersion}
                objectFit="cover"
                sx={{ borderRadius: 2, height: { xs: 220, md: 320 } }}
              />
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 900 }}>
              {query.data.title}
            </Typography>
            <Box
              sx={{ "& img": { maxWidth: "100%", height: "auto" }, typography: "body1" }}
              dangerouslySetInnerHTML={{ __html: sanitized }}
            />
          </Box>
        </Fade>
      )}
    </Box>
  )
}
