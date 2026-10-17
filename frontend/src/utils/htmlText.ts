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

type CachedAppPolicy = {
  createHTML: (value: string) => unknown
}

type TrustedTypesWindow = Window & {
  trustedTypes?: object
  __ttAppPolicy?: CachedAppPolicy | false
}

const parseTextWithDOMParser = (markup: unknown): string =>
  new DOMParser().parseFromString(markup as string, "text/html").body.textContent ?? ""

export const htmlToPlainText = (html: string | null | undefined): string => {
  // Both paths return "" for an empty source.
  const source = html ?? ""

  if (typeof DOMParser === "undefined") return stripTagsByState(source)

  const win = typeof window === "undefined" ? undefined : (window as TrustedTypesWindow)
  if (win?.trustedTypes) {
    // DOMParser.parseFromString is a Trusted Types sink under the production
    // CSP. Reuse only the already-created, finite `app` policy, whose createHTML
    // callback sanitizes through WASM; never create a new policy or pass raw
    // strings to the sink when TT is active.
    const policy = win.__ttAppPolicy
    if (!policy) return stripTagsByState(source)

    try {
      return parseTextWithDOMParser(policy.createHTML(source))
    } catch {
      // Match the server/no-DOMParser fallback if policy sanitization is not
      // available yet (for example, before the WASM sanitizer initializes).
      return stripTagsByState(source)
    }
  }

  return parseTextWithDOMParser(source)
}
