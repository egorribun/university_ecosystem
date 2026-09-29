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
  // Both paths return "" for an empty source.
  const source = html ?? ""

  if (typeof DOMParser !== "undefined") {
    return new DOMParser().parseFromString(source, "text/html").body.textContent ?? ""
  }

  return stripTagsByState(source)
}
