/**
 * Lightweight ambient layer retained for API compatibility with auth surfaces.
 *
 * The previous implementation ran a permanent 1,000-particle canvas simulation.
 * Authentication benefits from a calm, predictable surface more than decorative
 * motion, so production and test builds intentionally share this static layer.
 */
const ParticleAuthBackground = () => (
  <div className="pointer-events-none absolute inset-0 z-hide overflow-hidden" aria-hidden="true">
    <div className="absolute inset-0 bg-linear-to-b from-transparent via-transparent to-(--bg-page) opacity-strong" />
  </div>
)

export default ParticleAuthBackground
