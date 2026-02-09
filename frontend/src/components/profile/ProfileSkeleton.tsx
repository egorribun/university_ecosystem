import { Skeleton, Card } from "@/components/ui"
import Layout from "@/components/Layout"
import PageFadeIn from "@/components/PageFadeIn"

export const ProfileSkeleton = () => {
  return (
    <Layout>
      <PageFadeIn>
        <div className="max-w-[1400px] mx-auto w-full px-4 py-12">
          <Card className="overflow-hidden">
            <div className="h-64 relative">
              <Skeleton width="100%" height="100%" />
              <div className="absolute -bottom-16 left-1/2 -translate-x-1/2">
                <Skeleton
                  width={160}
                  height={160}
                  rounded="50%"
                  className="border-4 border-white"
                />
              </div>
            </div>
            <div className="pt-20 px-4 sm:px-12 pb-12 space-y-6">
              <div className="space-y-2">
                <Skeleton width={300} height={48} />
                <Skeleton width={200} height={24} />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} width="100%" height={48} rounded="12px" />
                  ))}
                </div>
                <div className="space-y-4">
                  <Skeleton width="100%" height={120} rounded="16px" />
                  <Skeleton width="100%" height={200} rounded="16px" />
                </div>
              </div>
            </div>
          </Card>
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default ProfileSkeleton
