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

const baseUser = {
  id: "user-1",
  full_name: "Тестовый Пользователь",
  email: "user@example.com",
  role: "student",
  group_id: "group-1",
  telegram: "@testuser",
  about: "Студент ГУУ",
  achievements: "Победитель олимпиады|ГУУ|2023",
  institute: "Институт цифровых технологий",
  course: "3",
  record_book_number: "123456",
  status: "Студент",
  program: "Информатика",
  track: "Разработка",
  department: "Кафедра ИТ",
  position: "",
  avatar_url: "",
  cover_url: "",
  spotify_connected: false,
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
        <AuthContext.Provider value={authValue}>{children}</AuthContext.Provider>
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
