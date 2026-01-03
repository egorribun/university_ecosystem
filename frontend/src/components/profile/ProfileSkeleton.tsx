import { memo } from "react"
import { Skeleton, Card } from "@/components/ui"

/**
 * ProfileSkeleton - Loading state for the Profile page.
 * Displays placeholder elements matching the profile layout.
 */
export function ProfileSkeleton() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Cover & Avatar */}
      <div className="relative mb-20">
        <Skeleton height={200} className="w-full rounded-t-2xl" ariaLabel="Loading cover" />
        <div className="absolute -bottom-16 left-6">
          <Skeleton
            width={128}
            height={128}
            rounded="50%"
            className="border-4 border-[var(--card-bg)]"
            ariaLabel="Loading avatar"
          />
        </div>
      </div>

      {/* Name & Role */}
      <div className="mb-8 space-y-3">
        <Skeleton width={200} height={28} ariaLabel="Loading name" />
        <Skeleton width={120} height={18} ariaLabel="Loading role" />
      </div>

      {/* Stats Row */}
      <div className="mb-8 flex gap-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="text-center">
            <Skeleton width={48} height={32} className="mb-1" />
            <Skeleton width={64} height={14} />
          </div>
        ))}
      </div>

      {/* About Section */}
      <Card className="mb-6 p-5">
        <Skeleton width="30%" height={20} className="mb-4" />
        <div className="space-y-2">
          <Skeleton width="100%" height={14} />
          <Skeleton width="85%" height={14} />
          <Skeleton width="70%" height={14} />
        </div>
      </Card>

      {/* Details Grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="p-4">
            <Skeleton width="40%" height={14} className="mb-2" />
            <Skeleton width="70%" height={18} />
          </Card>
        ))}
      </div>

      {/* Spotify Section */}
      <Card className="mt-6 p-5">
        <div className="flex items-center gap-4">
          <Skeleton width={56} height={56} rounded="12px" />
          <div className="flex-1 space-y-2">
            <Skeleton width="60%" height={18} />
            <Skeleton width="40%" height={14} />
          </div>
        </div>
      </Card>
    </div>
  )
}

export default memo(ProfileSkeleton)
