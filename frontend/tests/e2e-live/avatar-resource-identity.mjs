const VERSION_PARAM = "_v"
const GRAVATAR_HOST = "gravatar.com"

function isGravatar(hostname) {
  return hostname === GRAVATAR_HOST || hostname.endsWith(`.${GRAVATAR_HOST}`)
}

function parseBaseOrigin(value) {
  if (typeof value !== "string" || value.trim() === "") return null
  try {
    const parsed = new globalThis.URL(value)
    if (
      (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
      parsed.username !== "" ||
      parsed.password !== ""
    ) {
      return null
    }
    return parsed.origin
  } catch {
    return null
  }
}

function parseImageUrl(value, origin) {
  if (typeof value !== "string" || value.trim() === "") return null
  try {
    const parsed = new globalThis.URL(value, origin)
    if (
      (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
      parsed.username !== "" ||
      parsed.password !== "" ||
      isGravatar(parsed.hostname)
    ) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

function queryWithoutVersion(url) {
  return Array.from(url.searchParams.entries()).filter(([key]) => key !== VERSION_PARAM)
}

function sameQuery(left, right) {
  const leftEntries = queryWithoutVersion(left)
  const rightEntries = queryWithoutVersion(right)
  return (
    leftEntries.length === rightEntries.length &&
    leftEntries.every(([key, value], index) => {
      const other = rightEntries[index]
      return other !== undefined && key === other[0] && value === other[1]
    })
  )
}

function sameRenderedResource(savedSource, reloadedSource, baseOrigin) {
  const saved = parseImageUrl(savedSource, baseOrigin)
  const reloaded = parseImageUrl(reloadedSource, baseOrigin)
  if (!saved || !reloaded) return false

  const savedVersions = saved.searchParams.getAll(VERSION_PARAM)
  const reloadedVersions = reloaded.searchParams.getAll(VERSION_PARAM)
  return (
    savedVersions.length === 1 &&
    reloadedVersions.length === 1 &&
    saved.origin === reloaded.origin &&
    saved.pathname === reloaded.pathname &&
    saved.hash === reloaded.hash &&
    sameQuery(saved, reloaded)
  )
}

/** Compare two rendered avatar URLs while allowing only the _v cache token to change. */
export function renderedAvatarResourceMatches(savedRenderedSrc, reloadedRenderedSrc, baseUrl) {
  const baseOrigin = parseBaseOrigin(baseUrl)
  return (
    baseOrigin !== null && sameRenderedResource(savedRenderedSrc, reloadedRenderedSrc, baseOrigin)
  )
}

/** Compare owner persistence separately from the rendered URL's cache version. */
export function comparePersistedAvatarIdentity({
  savedProfileAvatarUrl,
  reloadedProfileAvatarUrl,
  savedRenderedSrc,
  reloadedRenderedSrc,
  baseUrl,
}) {
  const profileValueMatches =
    typeof savedProfileAvatarUrl === "string" &&
    savedProfileAvatarUrl.trim() !== "" &&
    savedProfileAvatarUrl === reloadedProfileAvatarUrl

  return {
    profileValueMatches,
    renderedSourceMatches: renderedAvatarResourceMatches(
      savedRenderedSrc,
      reloadedRenderedSrc,
      baseUrl
    ),
  }
}
