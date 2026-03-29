import { createRootRouteWithContext, Outlet } from "@tanstack/react-router"
import type { RouterContext } from "@/router"
import MainLayout from "@/components/layout/MainLayout"
import BackToTop from "@/components/motion/BackToTop"
import InstallPrompt from "@/components/pwa/InstallPrompt"
import LivePushToasts from "@/components/feedback/LivePushToasts"
import OfflineIndicator from "@/components/feedback/OfflineIndicator"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"
import { SearchDialog } from "@/components/search/SearchDialog"

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootComponent,
})

function RootComponent() {
  return (
    <MainLayout>
      <PageErrorBoundary>
        <Outlet />
      </PageErrorBoundary>

      <SearchDialog />
      <BackToTop />
      <LivePushToasts />
      <OfflineIndicator />
      <InstallPrompt />
    </MainLayout>
  )
}
