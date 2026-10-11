export function replacePrecacheRevision(
  workerSource: string,
  appBundlePath: string,
  revision: string
): string {
  const relativePath = appBundlePath.replace(/^\//u, "")
  const pathIndexes: number[] = []
  let searchFrom = 0
  while (true) {
    const index = workerSource.indexOf(relativePath, searchFrom)
    if (index < 0) break
    pathIndexes.push(index)
    searchFrom = index + relativePath.length
  }

  const entries = pathIndexes.flatMap((index) => {
    const start = workerSource.lastIndexOf("{", index)
    const end = workerSource.indexOf("}", index)
    if (start < 0 || end < 0) return []

    const entry = workerSource.slice(start, end + 1)
    // Workbox emits JSON-style quoted keys, with revision before url. Accept
    // that generated form as well as the bare-key form used by older builds.
    const urlMatch = entry.match(/(?:^|[,{]\s*)(?:["\x27]url["\x27]|url)\s*:\s*(["\x27])(.*?)\1/u)
    const manifestUrl = urlMatch?.[2]
    if (!manifestUrl) return []

    try {
      const manifestPath = new URL(manifestUrl, "https://pwa-update.invalid").pathname
      return manifestPath === appBundlePath ? [{ start, end, entry }] : []
    } catch {
      return []
    }
  })

  if (entries.length !== 1) {
    throw new Error("Expected exactly one precache entry for the selected app bundle")
  }

  const manifestEntry = entries[0]
  if (!manifestEntry) {
    throw new Error("Expected exactly one precache entry for the selected app bundle")
  }
  const { start, end, entry } = manifestEntry
  const updatedEntry = entry.replace(
    /(["\x27]?revision["\x27]?\s*:\s*)(?:null|["\x27][^"\x27]*["\x27])/u,
    `$1${JSON.stringify(revision)}`
  )
  if (updatedEntry === entry) {
    throw new Error("The selected precache entry has no replaceable revision")
  }

  return `${workerSource.slice(0, start)}${updatedEntry}${workerSource.slice(end + 1)}`
}
