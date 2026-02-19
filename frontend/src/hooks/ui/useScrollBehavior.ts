import { useState } from "react"
import { useScroll, useMotionValueEvent } from "framer-motion"
import { NAVBAR_SCROLL_THRESHOLD } from "@/constants/scroll"

export const useScrollBehavior = () => {
  const [isScrolled, setIsScrolled] = useState(false)

  const { scrollY } = useScroll()
  useMotionValueEvent(scrollY, "change", (latest) => {
    const scrolled = latest > NAVBAR_SCROLL_THRESHOLD
    if (scrolled !== isScrolled) setIsScrolled(scrolled)
  })

  return { isScrolled }
}
