"use strict"

// Keep the Lighthouse assertion matrix and the post-collection privacy check
// on one route inventory.  The common assertion set intentionally excludes
// SEO: protected application routes are expected to be blocked by robots.txt,
// so a global SEO score floor would turn that privacy requirement into a false
// failure.
const publicSeoPathPrefixes = Object.freeze([
  "/404",
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/",
])

const protectedRoutePrefixes = Object.freeze([
  "/news",
  "/dashboard",
  "/events",
  "/activity",
  "/map",
  "/messenger",
  "/profile",
  "/schedule",
  "/settings",
  "/admin",
])

// Keep the expected Lighthouse collection inventory alongside the route
// classification contract.  Each shard passes its selected subset; the
// aggregate gate uses this complete list to reject partial/failed collections.
const defaultLhciPaths = Object.freeze([
  "/",
  "/login",
  "/dashboard",
  "/news",
  "/schedule",
  "/events",
  "/activity",
  "/map",
  "/messenger",
  "/404",
])

const escapeRegex = (value) => value.replace(/[|\\{}()[\]^$+*?.-]/gu, "\\$&")
const publicSeoAlternatives = publicSeoPathPrefixes.map(escapeRegex).join("|")
const publicSeoUrlPattern = `https?://[^/]+(?:${publicSeoAlternatives})(?:[/?#]|$)`

module.exports = Object.freeze({
  publicSeoMinScore: 0.9,
  publicSeoPathPrefixes,
  publicSeoUrlPattern,
  protectedRoutePrefixes,
  defaultLhciPaths,
})
