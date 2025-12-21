import type { Preview } from "@storybook/react-vite"
import { CssVarsProvider } from "@mui/material/styles"
import CssBaseline from "@mui/material/CssBaseline"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import theme from "../src/theme"
import i18n from "../src/i18n/config"
import { AuthContext } from "../src/contexts/AuthContext"

import "../src/assets/themes.css"
import "../src/styles/tailwind.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: 'light',
      values: [
        { name: 'light', value: '#E8F1FB' },
        { name: 'dark', value: '#060B14' },
      ],
    },
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <AuthContext.Provider value={{
            isAuth: true,
            user: { id: 1, full_name: "Mock User", email: "mock@example.com", role: "admin" } as any,
            loading: false,
            login: async () => null,
            logout: async () => { },
            setUser: () => { },
            refresh: async () => { },
            pendingMfa: null,
            submitMfaChallenge: async () => { },
            requireMfa: async () => null,
            resetEtagCache: () => { },
          }}>
            <MemoryRouter>
              <CssVarsProvider theme={theme} defaultMode="system">
                <CssBaseline />
                <div style={{ padding: '2rem', minHeight: '100vh', background: 'var(--page-bg)' }}>
                  <Story />
                </div>
              </CssVarsProvider>
            </MemoryRouter>
          </AuthContext.Provider>
        </I18nextProvider>
      </QueryClientProvider>
    ),
  ],
}

export default preview