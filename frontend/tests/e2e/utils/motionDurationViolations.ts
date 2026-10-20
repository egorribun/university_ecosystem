export function collectMotionDurationViolations(root: Element) {
  const parseDurationMs = (value: string): number => {
    const trimmed = value.trim()
    if (trimmed.endsWith("ms")) return parseFloat(trimmed)
    if (trimmed.endsWith("s")) return parseFloat(trimmed) * 1000
    return 0
  }

  const exceedsDurationLimit = (value: string): boolean =>
    value.split(",").some((duration) => parseDurationMs(duration) > 1)

  const offenders: {
    selector: string
    transitionDuration: string
    animationDuration: string
  }[] = []

  for (const el of [root, ...root.querySelectorAll("*")]) {
    if (el.tagName.toLowerCase() === "svg") continue
    const styles = getComputedStyle(el)
    if (
      exceedsDurationLimit(styles.transitionDuration) ||
      exceedsDurationLimit(styles.animationDuration)
    ) {
      const id = (el as HTMLElement).id
      const classes = Array.from(el.classList).slice(0, 3).join(".")
      offenders.push({
        selector: `${el.tagName.toLowerCase()}${id ? "#" + id : ""}${classes ? "." + classes : ""}`,
        transitionDuration: styles.transitionDuration,
        animationDuration: styles.animationDuration,
      })
      if (offenders.length >= 10) break // cap output size
    }
  }

  return offenders
}
