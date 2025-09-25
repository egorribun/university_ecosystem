import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MobileBottomNav from "../MobileBottomNav";

describe("MobileBottomNav", () => {
  it("does not render on auth pages", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <MobileBottomNav />
      </MemoryRouter>
    );

    expect(screen.queryByRole("navigation", { name: "Основная навигация" })).toBeNull();
  });

  it("renders links for main sections", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <MobileBottomNav />
      </MemoryRouter>
    );

    const nav = screen.getByRole("navigation", { name: "Основная навигация" });
    expect(nav).toBeInTheDocument();
    expect(nav.querySelectorAll("a")).toHaveLength(5);
    expect(nav).toMatchSnapshot();
    expect(container).toMatchSnapshot();
  });
});
