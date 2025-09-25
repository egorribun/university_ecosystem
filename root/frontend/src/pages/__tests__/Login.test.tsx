import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import Login from "../Login";
import api from "../../api/axios";

vi.mock("../../api/axios", () => ({
  default: {
    post: vi.fn(),
  },
}));

const mockLogin = vi.fn();
const mockNavigate = vi.fn();

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ login: mockLogin }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("Login", () => {
  const mockedPost = vi.mocked(api.post);

  beforeEach(() => {
    mockedPost.mockReset();
    mockLogin.mockReset();
    mockNavigate.mockReset();
    localStorage.clear();
  });

  it("shows validation error for invalid email", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    await user.type(screen.getByRole("textbox", { name: /email/i }), "invalid");
    await user.type(screen.getByLabelText(/^пароль/i), "secret123");
    await user.click(screen.getByRole("button", { name: /войти/i }));

    expect(await screen.findByText("Введите корректный email")).toBeInTheDocument();
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it("submits credentials and navigates on success", async () => {
    const user = userEvent.setup();
    let resolvePost: (value: any) => void = () => {};
    mockedPost.mockImplementation(() => new Promise((resolve) => { resolvePost = resolve; }) as any);

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    await user.type(screen.getByRole("textbox", { name: /email/i }), "user@example.com");
    await user.type(screen.getByLabelText(/^пароль/i), "secret123");

    const submitButton = screen.getByRole("button", { name: /войти/i });
    await user.click(submitButton);

    expect(submitButton).toBeDisabled();

    resolvePost({ data: { access_token: "token123" } });

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith("token123"));
    expect(mockNavigate).toHaveBeenCalledWith("/dashboard");
    expect(submitButton).not.toBeDisabled();
  });
});
