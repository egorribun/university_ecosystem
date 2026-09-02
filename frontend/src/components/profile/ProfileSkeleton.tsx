import { Skeleton, Card } from "@/components/ui"
import Layout from "@/components/Layout"
import PageFadeIn from "@/components/motion/PageFadeIn"

export const ProfileSkeleton = () => {
  return (
    <Layout>
      <PageFadeIn>
        <div className="max-w-screen-2xl mx-auto w-full px-4 py-12">
          <Card className="overflow-hidden">
            <div className="h-64 relative">
              <Skeleton width="100%" height="100%" />
              <div className="absolute -bottom-16 left-1/2 -translate-x-1/2">
                <Skeleton
                  width={160}
                  height={160}
                  rounded="50%"
                  className="border-4 border-(--bg-surface)"
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
                    <Skeleton key={i} width="100%" height="3rem" rounded="md" />
                  ))}
                </div>
                <div className="space-y-4">
                  <Skeleton width="100%" height="7.5rem" rounded="lg" />
                  <Skeleton width="100%" height="12.5rem" rounded="lg" />
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
