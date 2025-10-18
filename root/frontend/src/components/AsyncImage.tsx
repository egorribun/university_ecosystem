import {
  forwardRef,
  useEffect,
  useMemo,
  useState,
  type ComponentProps,
  type CSSProperties,
  type ReactNode,
} from "react"
import InsertPhotoOutlinedIcon from "@mui/icons-material/InsertPhotoOutlined"
import { Box, Fade, Skeleton, type BoxProps } from "@mui/material"

import { addVersionParam } from "@/utils/media"

type Status = "idle" | "loading" | "loaded" | "error"

type AsyncImageProps = Omit<BoxProps, "component" | "onError" | "onLoad"> & {
  src?: string
  alt?: string
  fallbackSrc?: string
  fallback?: ReactNode
  thumbSrc?: string
  objectFit?: CSSProperties["objectFit"]
  version?: number
  onLoad?: ComponentProps<"img">["onLoad"]
  onError?: ComponentProps<"img">["onError"]
}

const fallbackStyles = {
  alignItems: "center",
  backgroundColor: (theme: any) => theme.palette.action.hover,
  color: (theme: any) => theme.palette.text.disabled,
  display: "flex",
  fontSize: "0.875rem",
  fontWeight: 500,
  inset: 0,
  justifyContent: "center",
  position: "absolute" as const,
}

const imageStyles = {
  display: "block",
  height: "100%",
  left: 0,
  position: "absolute" as const,
  top: 0,
  width: "100%",
}

const AsyncImage = forwardRef<HTMLImageElement, AsyncImageProps>(
  (
    {
      src,
      alt = "",
      fallbackSrc,
      fallback,
      thumbSrc,
      objectFit = "cover",
      version,
      onLoad,
      onError,
      sx,
      ...rest
    },
    ref
  ) => {
    const [status, setStatus] = useState<Status>(src ? "loading" : "idle")

    const resolvedSrc = useMemo(() => {
      if (!src) return ""
      return version != null ? addVersionParam(src, version) : src
    }, [src, version])

    useEffect(() => {
      setStatus(resolvedSrc ? "loading" : "idle")
    }, [resolvedSrc])

    const handleLoad: ComponentProps<"img">["onLoad"] = (event) => {
      setStatus("loaded")
      onLoad?.(event)
    }

    const handleError: ComponentProps<"img">["onError"] = (event) => {
      setStatus("error")
      onError?.(event)
    }

    const shouldShowSkeleton = status === "loading"
    const shouldShowFallback = status === "error" || (!resolvedSrc && fallback)
    const hasImage = Boolean(resolvedSrc)

    return (
      <Box
        position="relative"
        sx={{
          overflow: "hidden",
          borderRadius: 1,
          backgroundColor: (theme) => theme.palette.background.paper,
          ...sx,
        }}
        {...rest}
      >
        {shouldShowSkeleton && (
          <Skeleton
            variant="rectangular"
            data-testid="async-image-skeleton"
            sx={{ height: "100%", width: "100%", position: "absolute", inset: 0 }}
          />
        )}

        {thumbSrc && status === "loading" && (
          <Box
            component="img"
            src={thumbSrc}
            alt=""
            aria-hidden
            sx={{
              ...imageStyles,
              objectFit,
              filter: "blur(8px)",
              transform: "scale(1.05)",
            }}
          />
        )}

        {hasImage && (
          <Fade
            in={status === "loaded" || status === "loading"}
            timeout={{ enter: 300, exit: 200 }}
          >
            <Box
              component="img"
              ref={ref}
              src={resolvedSrc}
              alt={alt}
              loading="lazy"
              decoding="async"
              onLoad={handleLoad}
              onError={handleError}
              data-testid="async-image-img"
              sx={{ ...imageStyles, objectFit }}
            />
          </Fade>
        )}

        {!hasImage && fallbackSrc && (
          <Box
            component="img"
            src={fallbackSrc}
            alt={alt}
            aria-hidden={alt ? undefined : true}
            data-testid="async-image-fallback-image"
            sx={{ ...imageStyles, objectFit }}
          />
        )}

        {((shouldShowFallback && fallback) ||
          status === "error" ||
          (!hasImage && !fallbackSrc)) && (
          <Box sx={fallbackStyles} data-testid="async-image-fallback">
            {fallback ?? <InsertPhotoOutlinedIcon fontSize="large" />}
          </Box>
        )}
      </Box>
    )
  }
)

AsyncImage.displayName = "AsyncImage"

export default AsyncImage
