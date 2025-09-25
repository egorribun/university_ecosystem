import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import ResetPassword from "../ResetPassword";
import api from "../../api/axios";

vi.mock("../../api/axios", () => ({
  default: {
    post: vi.fn(),
  },
}));

vi.mock("zxcvbn", () => ({
  default: () => ({ score: 3, feedback: { warning: "", suggestions: [] } }),
}));

describe("ResetPassword", () => {
  const mockedPost = vi.mocked(api.post);
  const digestMock = vi.fn(() => Promise.resolve(new ArrayBuffer(20)));

  beforeEach(() => {
    mockedPost.mockReset();
    digestMock.mockClear();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, text: () => Promise.resolve("") }) as any));
    if (globalThis.crypto && globalThis.crypto.subtle) {
      vi.spyOn(globalThis.crypto.subtle, "digest").mockImplementation(digestMock as any);
    } else {
      (globalThis as any).crypto = { subtle: { digest: digestMock } };
    }
  });

  const renderWithToken = () =>
    render(
      <MemoryRouter initialEntries={["/reset/token123"]}>
        <Routes>
          <Route path="/reset/:token" element={<ResetPassword />} />
        </Routes>
      </MemoryRouter>
    );

  it("shows API error message when request fails", async () => {
    const user = userEvent.setup();
    mockedPost.mockRejectedValue({ response: { data: { detail: "Ссылка устарела" } } });

    renderWithToken();

    await user.type(screen.getByLabelText(/^пароль$/i), "Password123!");
    await user.type(screen.getByLabelText(/повторите пароль/i), "Password123!");
    await user.click(screen.getByRole("button", { name: /сохранить пароль/i }));

    expect(await screen.findByText("Ссылка устарела")).toBeInTheDocument();
  });

  it("submits new password and shows success message", async () => {
    const user = userEvent.setup();
    mockedPost.mockResolvedValue({ data: {} } as any);

    renderWithToken();

    await user.type(screen.getByLabelText(/^пароль$/i), "Password123!");
    await user.type(screen.getByLabelText(/повторите пароль/i), "Password123!");

    const submitButton = screen.getByRole("button", { name: /сохранить пароль/i });
    await user.click(submitButton);

    expect(submitButton).toBeDisabled();

    await waitFor(() => expect(mockedPost).toHaveBeenCalledWith("/password/reset", {
      password: "Password123!",
      token: "token123",
    }));

    expect(await screen.findByText(/пароль обновлён/i)).toBeInTheDocument();
  });
});
