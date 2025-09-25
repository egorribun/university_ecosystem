import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import Register from "../Register";
import api from "../../api/axios";

vi.mock("../../api/axios", () => ({
  default: {
    post: vi.fn(),
  },
}));

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("Register", () => {
  const mockedPost = vi.mocked(api.post);

  beforeEach(() => {
    mockedPost.mockReset();
    mockNavigate.mockReset();
  });

  it("shows API error message when registration fails", async () => {
    const user = userEvent.setup();
    mockedPost.mockRejectedValue({ response: { data: { detail: "Email already used" } } });

    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText("Имя"), "Test User");
    await user.type(screen.getByLabelText(/e-mail/i), "user@example.com");
    await user.type(screen.getByLabelText(/^пароль$/i), "password123");
    await user.type(screen.getByLabelText(/повторите пароль/i), "password123");

    await user.click(screen.getByRole("button", { name: /зарегистрироваться/i }));

    expect(await screen.findByText("Email already used")).toBeInTheDocument();
  });

  it("submits registration data and navigates on success", async () => {
    const user = userEvent.setup();
    let resolvePost: (value: any) => void = () => {};
    mockedPost.mockImplementation(() => new Promise((resolve) => { resolvePost = resolve; }) as any);

    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText("Имя"), "Test User");
    await user.type(screen.getByLabelText(/e-mail/i), "user@example.com");
    await user.type(screen.getByLabelText(/^пароль$/i), "password123");
    await user.type(screen.getByLabelText(/повторите пароль/i), "password123");

    const submitButton = screen.getByRole("button", { name: /зарегистрироваться/i });
    await user.click(submitButton);

    expect(submitButton).toBeDisabled();

    resolvePost({ data: {} });

    await waitFor(() => expect(mockedPost).toHaveBeenCalledWith("/users", {
      full_name: "Test User",
      email: "user@example.com",
      password: "password123",
      role: "student",
      invite_code: "",
    }));
    expect(mockNavigate).toHaveBeenCalledWith("/login");
    await waitFor(() => expect(submitButton).not.toBeDisabled());
  });
});
