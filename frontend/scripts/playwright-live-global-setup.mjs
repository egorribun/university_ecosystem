function localURL(name, protocols) {
  const value = process.env[name]
  if (!value) {
    throw new Error(`${name} must be set to the endpoint printed by scripts/live_stand.py`)
  }

  let parsed
  try {
    parsed = new URL(value)
  } catch {
    throw new Error(`${name} must be a valid loopback URL`)
  }
  if (
    !protocols.includes(parsed.protocol) ||
    !["localhost", "127.0.0.1"].includes(parsed.hostname) ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    !parsed.port ||
    Number(parsed.port) < 20_000 ||
    Number(parsed.port) > 45_000 ||
    parsed.pathname !== "/" ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new Error(`${name} must use an allowed protocol and an explicit live-stand loopback port`)
  }
  return parsed.toString().replace(/\/$/, "")
}

export default function validateLiveStandEnvironment() {
  localURL("LIVE_BASE_URL", ["https:", "http:"])
  localURL("LIVE_MAILPIT_URL", ["http:"])
}
