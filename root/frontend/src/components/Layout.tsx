import { ReactNode } from "react"

type LayoutProps = {
  children: ReactNode
}

const Layout = ({ children }: LayoutProps) => (
  <main
    id="main"
    className="min-h-screen w-screen box-border bg-[var(--page-bg)] text-[var(--page-text)]"
  >
    {children}
  </main>
)

export default Layout
