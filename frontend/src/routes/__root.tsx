import { createRootRouteWithContext, Outlet } from "@tanstack/react-router"
import type { RouterContext } from "@/router"
import MainLayout from "@/components/layout/MainLayout"
import BackToTop from "@/components/BackToTop"
import InstallPrompt from "@/components/InstallPrompt"
import LivePushToasts from "@/components/LivePushToasts"
import OfflineIndicator from "@/components/OfflineIndicator"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"
import { SearchDialog } from "@/components/SearchDialog"

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
