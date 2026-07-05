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

  if (typeof DOMParser !== "undefined") {
    return new DOMParser().parseFromString(source, "text/html").body.textContent ?? ""
  }

  return stripTagsByState(source)
}
