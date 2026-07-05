const stripTagsByState = (html: string): string => {
  let output = ""
  let insideTag = false

  for (const char of html) {
    if (char === "<") {
      insideTag = true
      continue
    }
    if (char === ">") {
      insideTag = false
      continue
    }
    if (!insideTag) output += char
  }

  return output
}

export const htmlToPlainText = (html: string | null | undefined): string => {
  const source = html ?? ""
  if (!source) return ""

  if (typeof document !== "undefined") {
    const template = document.createElement("template")
    template.innerHTML = source
    return template.content.textContent ?? ""
  }

  return stripTagsByState(source)
}
