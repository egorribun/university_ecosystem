import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { Experimental_CssVarsProvider as CssVarsProvider } from "@mui/material/styles";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import api from "@/api/client";
import { createQueryClient } from "@/app/queryClient";
import { AuthContext } from "@/contexts/AuthContext";
import Settings from "@/pages/Settings";

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => ({ unreadCount: 0 }),
}));

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: () => ({
    topicKeys: [],
    topicState: {},
    pushSupported: false,
    notificationPermission: "default" as NotificationPermission,
    notificationsEnabled: false,
    pushBusy: false,
    pushInitializing: false,
    permissionText: "",
    selectedTopicsDescription: "",
    enableNotifications: vi.fn(),
    disableNotifications: vi.fn(),
    handleTopicToggle: () => () => {},
    safariIOS: false,
    safariGuideUrl: "#",
  }),
  NOTIFICATION_TOPIC_LABELS: {},
}));

const baseUser = {
  id: 1,
  full_name: "Test User",
  email: "test@example.com",
  role: "student",
  avatar_url: "/media/avatars/original.png",
  cover_url: "/media/covers/original.jpg",
  spotify_connected: false,
  spotify_is_connected: false,
};

const renderSettings = () => {
  const queryClient = createQueryClient();
  const mockSetUser = vi.fn();
  const mockLogout = vi.fn().mockResolvedValue(undefined);

  const utils = render(
    <MemoryRouter initialEntries={["/settings"]}>
      <QueryClientProvider client={queryClient}>
        <CssVarsProvider>
          <AuthContext.Provider
            value={{
              user: baseUser,
              setUser: mockSetUser,
              logout: mockLogout,
              login: vi.fn(),
              isAuth: true,
              loading: false,
            }}
          >
            <Settings />
          </AuthContext.Provider>
        </CssVarsProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );

  return { ...utils, mockSetUser };
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("Settings media actions", () => {
  it("uploads avatar and refreshes the profile", async () => {
    const updatedUser = { ...baseUser, avatar_url: "/media/avatars/new.png" };
    const postSpy = vi.spyOn(api, "post").mockResolvedValue({ data: updatedUser } as any);
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: updatedUser } as any);

    const { mockSetUser } = renderSettings();

    fireEvent.click(screen.getByRole("tab", { name: "Аккаунт" }));

    await waitFor(() => expect(document.querySelectorAll("input[type='file']").length).toBeGreaterThan(1));
    const fileInputs = document.querySelectorAll<HTMLInputElement>("input[type='file']");

    const avatar = await screen.findByAltText(baseUser.full_name);
    const initialSrc = avatar.getAttribute("src");

    const file = new File(["avatar"], "avatar.png", { type: "image/png" });

    await act(async () => {
      fireEvent.change(fileInputs[0], { target: { files: [file] } });
      await new Promise((resolve) => setTimeout(resolve, 15));
    });

    await waitFor(() => expect(postSpy).toHaveBeenCalled());

    const formData = postSpy.mock.calls[0][1] as FormData;
    expect(formData.get("file")).toBe(file);

    await waitFor(() => expect(getSpy).toHaveBeenCalledWith("/users/me"));
    await waitFor(() => expect(mockSetUser).toHaveBeenCalledWith(updatedUser));

    const updatedSrc = avatar.getAttribute("src");
    expect(updatedSrc).toContain("v=");
    expect(updatedSrc).not.toEqual(initialSrc);
  });

  it("shows an error when avatar upload fails", async () => {
    vi.spyOn(api, "post").mockRejectedValue({ response: { data: { detail: "Ошибка загрузки" } } });

    renderSettings();
    fireEvent.click(screen.getByRole("tab", { name: "Аккаунт" }));
    await waitFor(() => expect(document.querySelector("input[type='file']")).toBeTruthy());
    const fileInputs = document.querySelectorAll<HTMLInputElement>("input[type='file']");
    const file = new File(["avatar"], "avatar.png", { type: "image/png" });

    await act(async () => {
      fireEvent.change(fileInputs[0], { target: { files: [file] } });
    });

    await waitFor(() => expect(api.post).toHaveBeenCalled());

    expect(await screen.findByText("Не удалось загрузить аватар", {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it("uploads cover and updates preview", async () => {
    const updatedUser = { ...baseUser, cover_url: "/media/covers/new.jpg" };
    vi.spyOn(api, "post").mockImplementation((url: string) => {
      if (url === "/users/me/cover") {
        return Promise.resolve({ data: updatedUser } as any);
      }
      return Promise.resolve({ data: updatedUser } as any);
    });
    vi.spyOn(api, "get").mockResolvedValue({ data: updatedUser } as any);

    const { mockSetUser } = renderSettings();

    fireEvent.click(screen.getByRole("tab", { name: "Аккаунт" }));

    await waitFor(() => expect(document.querySelectorAll("input[type='file']").length).toBeGreaterThan(1));
    const fileInputs = document.querySelectorAll<HTMLInputElement>("input[type='file']");

    const coverLabel = await screen.findByText("Обложка профиля");
    const coverItem = coverLabel.closest("li") as HTMLElement;
    const preview = coverItem.querySelector<HTMLElement>("[data-testid='settings-cover-preview']");
    expect(preview).toBeTruthy();
    const initialBackground = window.getComputedStyle(preview!).backgroundImage;

    const file = new File(["cover"], "cover.png", { type: "image/png" });
    await act(async () => {
      fireEvent.change(fileInputs[1], { target: { files: [file] } });
      await new Promise((resolve) => setTimeout(resolve, 15));
    });

    await waitFor(() => expect(api.post).toHaveBeenCalled());

    await waitFor(() => expect(mockSetUser).toHaveBeenCalledWith(updatedUser));

    const updatedBackground = window.getComputedStyle(preview!).backgroundImage;
    expect(updatedBackground).toContain("v=");
    expect(updatedBackground).not.toEqual(initialBackground);
  });
});
