interface DeviceProfile {
  deviceMemory?: number
  hardwareConcurrency?: number
  connection?: {
    saveData?: boolean
  }
}

const CONSTRAINED_MEMORY_GB = 4
const CONSTRAINED_CPU_CORES = 4

/** Returns true only when the browser exposes an explicit constrained signal. */
export function isLowPowerDevice(
  profile: DeviceProfile = typeof navigator === "undefined"
    ? {}
    : (navigator as Navigator & DeviceProfile)
): boolean {
  if (profile.connection?.saveData === true) return true
  if (typeof profile.deviceMemory === "number" && profile.deviceMemory <= CONSTRAINED_MEMORY_GB) {
    return true
  }
  return (
    typeof profile.hardwareConcurrency === "number" &&
    profile.hardwareConcurrency <= CONSTRAINED_CPU_CORES
  )
}
