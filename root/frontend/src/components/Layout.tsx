import { Box } from "@mui/material"
import { ReactNode } from "react"

type LayoutProps = {
  children: ReactNode
}

const Layout = ({ children }: LayoutProps) => (
  <Box
    sx={{
      minHeight: "100vh",
      bgcolor: "var(--page-bg)",
      color: "var(--page-text)",
      width: "100vw",
      boxSizing: "border-box",
    }}
  >
    {children}
  </Box>
)

export default Layout