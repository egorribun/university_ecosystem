// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
// Wave 43: Migrated from Framer Motion to CSS @keyframes — zero JS for decorative loops
export function NewsCardBackground() {
  return (
    <>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-hide mix-blend-soft-light transition-opacity duration-slow motion-reduce:!animate-none"
        style={{
          background:
            "radial-gradient(circle at top right, var(--dash-card-news-radial), transparent 68%)",
          animation: "orb-breathe 4.5s ease-in-out infinite",
        }}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-20 left-1/3 z-hide h-44 w-44 rounded-full opacity-(--opacity-medium) blur-3xl mix-blend-soft-light transition-opacity duration-slower motion-reduce:!animate-none"
        style={{
          background:
            "radial-gradient(circle, var(--dash-card-news-orb), transparent)",
          animation: "orb-drift 6.5s ease-in-out infinite",
        }}
      />
    </>
  )
}
