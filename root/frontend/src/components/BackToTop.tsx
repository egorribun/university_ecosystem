import { useEffect, useState, useCallback } from "react"
import { useTranslation } from "react-i18next"

export default function BackToTop() {
  const { t } = useTranslation(["common"])
  const [show, setShow] = useState(false)
  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 420)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])
  const onClick = useCallback(() => {
    try {
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch {
      window.scrollTo(0, 0)
    }
  }, [])
  return (
    <button
      type="button"
      className={"back-to-top" + (show ? " visible" : "")}
      style={{ pointerEvents: show ? "auto" : "none" }}
      aria-label={t("common:buttons.backToTop")}
      onClick={onClick}
    >
      ↑
    </button>
  )
}
