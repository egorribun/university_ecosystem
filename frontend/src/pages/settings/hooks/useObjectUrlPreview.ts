import { useCallback, useEffect, useRef, useState } from "react"

export function useObjectUrlPreview() {
  const activeUrlRef = useRef<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const clearPreview = useCallback(() => {
    const activeUrl = activeUrlRef.current
    if (activeUrl) URL.revokeObjectURL(activeUrl)
    activeUrlRef.current = null
    setPreviewUrl(null)
  }, [])

  const beginPreview = useCallback(
    (file: File) => {
      clearPreview()
      const nextUrl = URL.createObjectURL(file)
      activeUrlRef.current = nextUrl
      setPreviewUrl(nextUrl)
    },
    [clearPreview]
  )

  useEffect(
    () => () => {
      const activeUrl = activeUrlRef.current
      if (activeUrl) URL.revokeObjectURL(activeUrl)
      activeUrlRef.current = null
    },
    []
  )

  return { previewUrl, beginPreview, clearPreview }
}
