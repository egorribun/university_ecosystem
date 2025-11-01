import { ReactNode } from "react"

type LayoutProps = {
  children: ReactNode
}

const Layout = ({ children }: LayoutProps) => (
  <main
    id="main"
    className="box-border min-h-screen w-full bg-[var(--page-bg)] text-[var(--page-text)]"
  >
    {children}
  </main>
)

export default Layout
