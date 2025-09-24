import { Box } from "@mui/material"
import { ReactNode } from "react"

type LayoutProps = {
  children: ReactNode
}

const Layout = ({ children }: LayoutProps) => (
  <Box
    component="main"
    sx={(theme) => ({
      minHeight: "100vh",
      bgcolor: theme.vars ? theme.vars.palette.background.default : theme.palette.background.default,
      color: theme.vars ? theme.vars.palette.text.primary : theme.palette.text.primary,
      width: "100vw",
      boxSizing: "border-box",
      transition: `background-color ${theme.app.transitions.medium}, color ${theme.app.transitions.medium}`,
    })}
  >
    {children}
  </Box>
)

export default Layout
