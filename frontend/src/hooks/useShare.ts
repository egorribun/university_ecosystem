import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { logError } from "@/app/logger"
import {
  Send as TelegramIcon,
  MessageCircle as WhatsAppIcon,
  Mail as AlternateEmailIcon,
} from "lucide-react"

interface ShareOptions {
  title: string
  url?: string
  onNotify?: (message: string) => void
  translations?: {
    shareSuccess?: string
    shareError?: string
    linkCopied?: string
    pageTitle?: string
    telegram?: string
    whatsapp?: string
    email?: string
  }
}

export function resolveShareUrl(url?: string): string {
  if (url) return url
  if (typeof window === "undefined") return ""
  return window.location.href
}

export function useShare({ title, url, onNotify, translations = {} }: ShareOptions) {
  const [sharing, setSharing] = useState(false)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [copyingLink, setCopyingLink] = useState(false)
  const [copiedLink, setCopiedLink] = useState(false)
  const copyTimeoutRef = useRef<number | null>(null)

  const shareUrl = useMemo(() => resolveShareUrl(url), [url])

  const shareOptions = useMemo(() => {
    if (!shareUrl) return []
    const encodedUrl = encodeURIComponent(shareUrl)
    const shareTitle = title || translations.pageTitle || "Share"
    const encodedTitle = encodeURIComponent(shareTitle)

    return [
      {
        id: "telegram",
        label: translations.telegram || "Telegram",
        href: `https://t.me/share/url?url=${encodedUrl}&text=${encodedTitle}`,
        icon: TelegramIcon,
        accent: "text-brand",
      },
      {
        id: "whatsapp",
        label: translations.whatsapp || "WhatsApp",
        href: `https://api.whatsapp.com/send?text=${encodedTitle}%20${encodedUrl}`,
        icon: WhatsAppIcon,
        accent: "text-(--success-text)",
      },
      {
        id: "email",
        label: translations.email || "Email",
        href: `mailto:?subject=${encodedTitle}&body=${encodedTitle}%0A${encodedUrl}`,
        icon: AlternateEmailIcon,
        accent: "text-brand/(--opacity-hover)",
      },
    ]
  }, [shareUrl, title, translations])

  const handleShare = useCallback(async () => {
    if (sharing) return

    const fullUrl = shareUrl
    if (!fullUrl) return

    const shareTitle = title || translations.pageTitle || "Share"
    const shareData = {
      title: shareTitle,
      text: shareTitle,
      url: fullUrl,
    }

    const canUseNativeShare =
      typeof navigator !== "undefined" &&
      typeof navigator.share === "function" &&
      (!navigator.canShare || navigator.canShare(shareData))

    try {
      setSharing(true)
      if (canUseNativeShare) {
        await navigator.share(shareData)
        onNotify?.(translations.shareSuccess || "Shared successfully")
      } else {
        setShareDialogOpen(true)
      }
    } catch (error) {
      const message = (error as DOMException | Error)?.name ?? ""
      if (message === "AbortError") return
      logError(error)
      onNotify?.(translations.shareError || "Share failed")
    } finally {
      setSharing(false)
    }
  }, [sharing, shareUrl, title, translations, onNotify])

  const handleCopyLink = useCallback(async () => {
    if (!shareUrl || copyingLink) return
    setCopyingLink(true)

    try {
      // RZ-43-02: Prefer Clipboard API; fall back to legacy only if truly unavailable.
      // document.execCommand("copy") is deprecated and may be blocked by CSP.
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl)
      } else if (typeof window !== "undefined" && window.isSecureContext === false) {
        // Non-secure contexts (HTTP) cannot use Clipboard API — warn instead of silently failing
        throw new Error("Clipboard API requires a secure context (HTTPS)")
      } else {
        throw new Error("Clipboard API not available")
      }

      setCopiedLink(true)
      onNotify?.(translations.linkCopied || "Link copied!")

      if (copyTimeoutRef.current) {
        window.clearTimeout(copyTimeoutRef.current)
      }
      copyTimeoutRef.current = window.setTimeout(() => {
        setCopiedLink(false)
        copyTimeoutRef.current = null
      }, 2200)
    } catch (error) {
      logError(error)
      onNotify?.(translations.shareError || "Copy failed")
    } finally {
      setCopyingLink(false)
    }
  }, [copyingLink, shareUrl, translations, onNotify])

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        window.clearTimeout(copyTimeoutRef.current)
        copyTimeoutRef.current = null
      }
    }
  }, [])

  return {
    sharing,
    shareDialogOpen,
    setShareDialogOpen,
    copyingLink,
    copiedLink,
    shareOptions,
    handleShare,
    handleCopyLink,
  }
}
