import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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

export function useShare({ title, url, onNotify, translations = {} }: ShareOptions) {
  const [sharing, setSharing] = useState(false)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [copyingLink, setCopyingLink] = useState(false)
  const [copiedLink, setCopiedLink] = useState(false)
  const copyTimeoutRef = useRef<number | null>(null)

  const shareUrl = useMemo(() => {
    if (url) return url
    if (typeof window === "undefined") return ""
    return window.location.href
  }, [url])

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
      console.error(error)
      onNotify?.(translations.shareError || "Share failed")
    } finally {
      setSharing(false)
    }
  }, [sharing, shareUrl, title, translations, onNotify])

  const handleCopyLink = useCallback(async () => {
    if (!shareUrl || copyingLink) return
    setCopyingLink(true)

    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl)
      } else {
        const textarea = document.createElement("textarea")
        textarea.value = shareUrl
        textarea.setAttribute("readonly", "")
        textarea.style.position = "absolute"
        textarea.style.left = "-9999px"
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand("copy")
        document.body.removeChild(textarea)
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
      console.error(error)
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
