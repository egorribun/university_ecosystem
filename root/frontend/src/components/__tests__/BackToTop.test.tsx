import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BackToTop from "../BackToTop";

const setScrollY = (value: number) => {
  Object.defineProperty(window, "scrollY", { value, configurable: true });
  Object.defineProperty(window, "pageYOffset", { value, configurable: true });
};

describe("BackToTop", () => {
  beforeEach(() => {
    setScrollY(0);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders hidden button by default", () => {
    const { container } = render(<BackToTop />);
    const button = screen.getByRole("button", { name: "Наверх" });
    expect(button).toBeInTheDocument();
    expect(button).not.toHaveClass("visible");
    expect(container.firstChild).toMatchSnapshot();
  });

  it("toggles visibility after scrolling", async () => {
    render(<BackToTop />);
    const button = screen.getByRole("button", { name: "Наверх" });

    setScrollY(500);
    fireEvent.scroll(window);

    await waitFor(() => expect(button).toHaveClass("visible"));

    setScrollY(0);
    fireEvent.scroll(window);

    await waitFor(() => expect(button).not.toHaveClass("visible"));
  });

  it("scrolls smoothly to top when clicked", () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    const { getByRole } = render(<BackToTop />);
    const button = getByRole("button", { name: "Наверх" });

    setScrollY(500);
    fireEvent.scroll(window);

    fireEvent.click(button);

    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
  });
});
