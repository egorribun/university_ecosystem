import { ThemeProvider, createTheme } from "@mui/material/styles";
import { render, act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NowPlayingCard } from "@/pages/Profile";
import type { NowPlaying } from "@/types/spotify";

vi.mock("framer-motion", async () => {
  const actual = await vi.importActual<typeof import("framer-motion")>("framer-motion");
  return { ...actual, useReducedMotion: () => false };
});

const theme = createTheme();

const baseTrack: NowPlaying = {
  is_playing: true,
  track_id: "play-1",
  track_name: "Test Track",
  artists: ["Tester"],
  album_name: "Album",
  album_image_url: "https://example.com/cover.jpg",
  track_url: "https://open.spotify.com/track/play-1",
  duration_ms: 180000,
  progress_ms: 30000,
  fetched_at: "2024-01-01T00:00:00.000Z",
};

const renderWithTheme = (track: NowPlaying) =>
  render(
    <ThemeProvider theme={theme}>
      <NowPlayingCard data={track} />
    </ThemeProvider>,
  );

describe("NowPlayingCard", () => {
  it("matches snapshot when playing", () => {
    const { container } = renderWithTheme(baseTrack);
    expect(container.firstChild).toMatchSnapshot();
  });

  it("matches snapshot when paused", () => {
    const paused: NowPlaying = { ...baseTrack, is_playing: false };
    const { container, getByText } = renderWithTheme(paused);
    expect(getByText("Пауза")).toBeInTheDocument();
    expect(container.firstChild).toMatchSnapshot();
  });

  it("formats progress and duration as mm:ss", () => {
    const extended: NowPlaying = { ...baseTrack, progress_ms: 65_000, duration_ms: 241_000 };
    const { getByText } = renderWithTheme(extended);
    expect(getByText("1:05 / 4:01")).toBeInTheDocument();
  });

  it("clamps invalid progress values before formatting", () => {
    const overflowing: NowPlaying = { ...baseTrack, progress_ms: 999_000, duration_ms: 90_000 };
    const { getByText, rerender } = renderWithTheme(overflowing);
    expect(getByText("1:30 / 1:30")).toBeInTheDocument();

    const negative: NowPlaying = { ...baseTrack, progress_ms: -5_000, duration_ms: 0 };
    rerender(
      <ThemeProvider theme={theme}>
        <NowPlayingCard data={negative} />
      </ThemeProvider>,
    );
    expect(getByText("0:00 / 0:00")).toBeInTheDocument();
  });

  it("reflects updated progress when data changes", () => {
    const { getByRole, rerender } = renderWithTheme(baseTrack);
    const progressBar = getByRole("progressbar");
    const initial = Number(progressBar.getAttribute("aria-valuenow"));

    const advanced: NowPlaying = {
      ...baseTrack,
      progress_ms: (baseTrack.progress_ms ?? 0) + 15000,
      fetched_at: "2024-01-01T00:00:15.000Z",
    };

    act(() => {
      rerender(
        <ThemeProvider theme={theme}>
          <NowPlayingCard data={advanced} />
        </ThemeProvider>,
      );
    });

    const updated = Number(progressBar.getAttribute("aria-valuenow"));
    expect(updated).toBeGreaterThan(initial);
  });
});
