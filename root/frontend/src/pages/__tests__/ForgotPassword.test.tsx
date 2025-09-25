import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import ForgotPassword from "../ForgotPassword";
import api from "../../api/axios";

vi.mock("../../api/axios", () => ({
  default: {
    post: vi.fn(),
  },
}));

describe("ForgotPassword", () => {
  const mockedPost = vi.mocked(api.post);

  beforeEach(() => {
    mockedPost.mockReset();
    vi.useRealTimers();
  });

  it("highlights invalid email format", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ForgotPassword />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/e-mail/i), "invalid");

    expect(screen.getByText("Неверный формат email")).toBeInTheDocument();
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it("shows confirmation message and cooldown on success", async () => {
    const user = userEvent.setup();
    mockedPost.mockResolvedValue({ data: {} } as any);
    render(
      <MemoryRouter>
        <ForgotPassword />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/e-mail/i), "user@example.com");
    await user.click(screen.getByRole("button", { name: /отправить ссылку/i }));

    expect(mockedPost).toHaveBeenCalledWith("/password/forgot", { email: "user@example.com" });
    expect(await screen.findByText(/если аккаунт с адресом/i)).toBeInTheDocument();

    const resetButton = screen.getByRole("button", { name: /ввести другой адрес/i });
    expect(resetButton).toBeDisabled();
    expect(resetButton.textContent).toContain("30s");
  });
});
