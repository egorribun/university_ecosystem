export function isIOS(): boolean {
  if (typeof navigator === "undefined") return false
  const platform = navigator.platform || ""
  const userAgent = navigator.userAgent || ""
  const iosPlatforms = ["iPad", "iPhone", "iPod"]
  if (iosPlatforms.includes(platform)) return true
  // iPadOS 13+ returns MacIntel, so additionally check for touch support
  if (platform === "MacIntel" && (navigator as any).maxTouchPoints > 1) return true
  return /iPad|iPhone|iPod/.test(userAgent)
}

export function isSafari(): boolean {
  if (typeof navigator === "undefined") return false
  const ua = navigator.userAgent || ""
  const vendor = navigator.vendor || ""
  const isSafariVendor = /Apple Computer/.test(vendor)
  const isSafariUA = /Safari/.test(ua)
  const isExcluded = /CriOS|FxiOS|OPiOS|EdgiOS|Chrome|Firefox|OPR|Edg/.test(ua)
  return isSafariUA && isSafariVendor && !isExcluded
}

export function isSafariIOS(): boolean {
  return isIOS() && isSafari()
}
