import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PropsWithChildren } from "react";
import { describe, it, beforeEach, afterEach, vi } from "vitest";

import Navbar from "@/components/Navbar";
import Dashboard from "@/pages/Dashboard";
import Profile from "@/pages/Profile";
import { AuthContext } from "@/contexts/AuthContext";
import { routerFutureFlags } from "@/App";
import { checkA11y } from "@/tests/axeTest";
import { createQueryClient } from "@/app/queryClient";
import api from "@/api/client";
import type { User } from "@/types/User";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { CssVarsProvider } from "@mui/material/styles";
import theme from "@/theme";

vi.mock("@/components/NotificationsBell", () => ({
  default: ({ iconColor }: { iconColor?: string }) => (
    <div data-testid="notifications-bell" data-color={iconColor ?? ""} />
  ),
}));

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => ({
    items: [],
    loading: false,
    unreadCount: 0,
    hasMore: false,
    loadMore: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    refresh: vi.fn(),
    fetching: false,
  }),
}));

vi.mock("@/hooks/useNowPlaying", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useNowPlaying")>(
    "@/hooks/useNowPlaying",
  );
  return {
    ...actual,
    useNowPlaying: () => ({
      data: null,
      status: "success",
      fetchStatus: "idle",
      isFetching: false,
      isLoading: false,
      isSuccess: true,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
  };
});

const baseUser: User = {
  id: 1,
  email: "user@example.com",
  full_name: "Тестовый Пользователь",
  role: "student",
  group_id: 1,
  avatar_url: "",
  cover_url: "",
  about: "Студент ГУУ",
  record_book_number: "123456",
  status: "Студент",
  institute: "Институт цифровых технологий",
  course: "3",
  education_level: null,
  track: "Разработка",
  program: "Информатика",
  telegram: "@testuser",
  achievements: "Победитель олимпиады|ГУУ|2023",
  department: "Кафедра ИТ",
  position: "",
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: false,
  dnd_enabled: false,
  dnd_start: null,
  dnd_end: null,
  is_active: true,
};

const activeClients: QueryClient[] = [];

const createWrapper = (route = "/dashboard") => {
  const queryClient = createQueryClient();
  activeClients.push(queryClient);
  const authValue = {
    isAuth: true,
    login: vi.fn(),
    logout: vi.fn(),
    setUser: vi.fn(),
    refresh: vi.fn(),
    loading: false,
    user: { ...baseUser },
  };

  const Wrapper = ({ children }: PropsWithChildren) => (
    <MemoryRouter future={routerFutureFlags} initialEntries={[route]}>
      <QueryClientProvider client={queryClient}>
        <CssVarsProvider theme={theme}>
          <LanguageProvider>
            <AuthContext.Provider value={authValue}>{children}</AuthContext.Provider>
          </LanguageProvider>
        </CssVarsProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );

  return { Wrapper };
};

describe("Accessibility checks", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn().mockReturnValue(false),
      }),
    });
  });

  afterEach(() => {
    activeClients.splice(0).forEach((client) => client.clear());
    vi.clearAllMocks();
  });

  it("Navbar has no axe violations", async () => {
    const { Wrapper } = createWrapper("/dashboard");
    const { container } = render(<Navbar />, { wrapper: Wrapper });

    await waitFor(() => expect(screen.getByRole("navigation")).toBeInTheDocument());

    await checkA11y(container);
  });

  it("Dashboard page has no axe violations", async () => {
    const getSpy = vi.spyOn(api, "get").mockImplementation(async () => ({ data: [] }) as any);

    const { Wrapper } = createWrapper("/dashboard");
    const { container } = render(<Dashboard />, { wrapper: Wrapper });

    await waitFor(() => expect(api.get).toHaveBeenCalled());

    await checkA11y(container);
    getSpy.mockRestore();
  });

  it("Profile page has no axe violations", async () => {
    const { Wrapper } = createWrapper("/profile");
    const { container } = render(<Profile />, { wrapper: Wrapper });

    await waitFor(() => expect(screen.getByTestId("profile-root")).toBeInTheDocument());

    await checkA11y(container);
  });
});
